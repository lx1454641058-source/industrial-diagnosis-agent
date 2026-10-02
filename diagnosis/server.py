"""Original loopback web service; no uploads, shell execution or device writes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import uuid
from urllib.parse import urlparse

from .acquisition import Collector, DemoBackend, SerialBackend
from .agent import Agent, OllamaProvider
from .protocol import Profile
from .storage import Store
from .tools import Toolset

ROOT = Path(__file__).resolve().parent.parent


class Application:
    def __init__(self, collector, agent):
        self.collector, self.agent = collector, agent
        self.jobs = {}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='diagnostic-agent')

    def submit(self, question):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
            raise ValueError('请输入 1～2000 字符的问题')
        with self.lock:
            if any(j['status'] in ['queued', 'running'] for j in self.jobs.values()):
                raise ValueError('已有诊断执行中，请等待本轮完成')
            key = uuid.uuid4().hex
            self.jobs[key] = {'status': 'queued', 'question': question, 'trace': []}
            while len(self.jobs) > 20:
                self.jobs.pop(next(iter(self.jobs)))

        def publish(result):
            with self.lock: self.jobs[key] = deepcopy(result)

        def run():
            publish({'status': 'running', 'question': question, 'trace': []})
            try:
                self.agent.run(question, publish)
            except Exception:
                publish({'status': 'failed', 'error': '诊断存储或执行失败，检查本地运行环境', 'trace': []})
        self.pool.submit(run)
        return key

    def get_job(self, key):
        with self.lock:
            return deepcopy(self.jobs.get(key))

    def close(self):
        self.collector.stop()
        self.pool.shutdown(wait=True)
        self.collector.store.close()


def create_server(app, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def send_json(self, value, code=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8', code)

        def send_bytes(self, data, mime, code=200):
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass

        def local_request(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected: return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + expected: return False
            return self.headers.get('Sec-Fetch-Site') not in ['cross-site']

        def do_GET(self):
            if not self.local_request():
                self.send_json({'error': '仅允许本机同源访问'}, 403); return
            path = urlparse(self.path).path
            if path in ['/', '/app.js', '/style.css']:
                filename, mime = {'/': ('index.html', 'text/html; charset=utf-8'),
                                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                                  '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
                self.send_bytes((ROOT / 'static' / filename).read_bytes(), mime); return
            if path == '/api/state':
                self.send_json({'sensor': app.collector.status(),
                                'provider': app.agent.provider.kind if app.agent.provider else 'rule_baseline',
                                'model': app.agent.provider.model if app.agent.provider else None,
                                'profile': app.collector.profile.name}); return
            if path == '/api/history':
                self.send_json({'samples': list(reversed(app.collector.store.samples(100)))}); return
            if path == '/api/reports':
                self.send_json({'reports': app.collector.store.sessions(10)}); return
            if path.startswith('/api/jobs/'):
                result = app.get_job(path.removeprefix('/api/jobs/'))
                self.send_json(result if result else {'error': '诊断任务不存在'}, 200 if result else 404); return
            self.send_json({'error': '页面不存在'}, 404)

        def do_POST(self):
            if not self.local_request():
                self.send_json({'error': '仅允许本机同源操作'}, 403); return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.send_json({'error': '需要 JSON 格式'}, 415); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 12000: raise ValueError('请求大小超出范围')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict): raise ValueError('请求必须是对象')
                if self.path == '/api/diagnose' and set(body) == {'question'}:
                    key = app.submit(body['question'])
                    self.send_json({'job_id': key}, 202); return
                if self.path == '/api/scenario' and set(body) == {'scenario'}:
                    if not isinstance(body['scenario'], str): raise ValueError('场景无效')
                    with app.lock:
                        if any(j['status'] in ['queued', 'running'] for j in app.jobs.values()):
                            raise ValueError('诊断期间不能切换模拟故障，避免证据跨场景混用')
                        app.collector.set_scenario(body['scenario'])
                        if app.collector.enabled: app.collector.read_once()
                    self.send_json({'ok': True}); return
                self.send_json({'error': '请求路径或字段不正确'}, 404)
            except (ValueError, UnicodeError) as exc:
                self.send_json({'error': str(exc)[:300]}, 400)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='工业采集故障排查智能体')
    parser.add_argument('--mode', choices=['demo', 'serial'], default='demo')
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--reference-profile', type=Path)
    parser.add_argument('--provider', choices=['baseline', 'ollama'], default='baseline')
    parser.add_argument('--model', default='')
    parser.add_argument('--model-url', default='http://127.0.0.1:11434')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--data-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.mode == 'serial' and not args.profile:
            raise ValueError('真实串口模式必须提供经过核对的 --profile 文件')
        values = json.loads(args.profile.read_text(encoding='utf-8-sig')) if args.profile else {}
        profile = Profile(**values).validate()
        reference = Profile(**json.loads(args.reference_profile.read_text(encoding='utf-8-sig'))).validate() if args.reference_profile else None
        if args.mode == 'serial' and reference and not reference.hardware_confirmed:
            raise ValueError('独立参考配置必须已由人工核对并确认 hardware_confirmed')
        backend = DemoBackend(profile) if args.mode == 'demo' else SerialBackend(profile)
        provider = OllamaProvider(args.model, args.model_url) if args.provider == 'ollama' else None
        # Per-mode and per-profile storage prevents simulated samples contaminating live history.
        import hashlib
        fingerprint = hashlib.sha256(json.dumps(profile.public(), sort_keys=True).encode()).hexdigest()[:12]
        data_dir = (args.data_dir or ROOT / 'work') / f'{args.mode}-{fingerprint}'
        store = Store(data_dir / 'evidence.sqlite3')
        collector = Collector(profile, backend, store, reference)
        app = Application(collector, Agent(Toolset(collector), store, provider))
        server = create_server(app, args.port)
    except (ValueError, TypeError, OSError) as exc:
        parser.error(str(exc))
    collector.start()
    print(f'工业采集诊断服务 http://127.0.0.1:{server.server_port}', flush=True)
    print(f'数据来源: {backend.source}; 诊断模式: {provider.kind if provider else "rule_baseline（非大模型）"}', flush=True)
    try: server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        app.close()


if __name__ == '__main__': main()
