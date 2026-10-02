"""Original collector/tool/agent regression and local HTTP integration tests."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from diagnosis.protocol import Profile
from diagnosis.acquisition import Collector, DemoBackend, SerialBackend
from diagnosis.agent import Agent, OllamaProvider, parse_final
from diagnosis.storage import Store
from diagnosis.tools import Toolset
from diagnosis.server import Application, create_server


@contextmanager
def fixture(start=True):
    with tempfile.TemporaryDirectory() as folder:
        p = Profile(interval=.5, stale_after=2)
        store = Store(Path(folder)/'evidence.sqlite3')
        collector = Collector(p, DemoBackend(p), store)
        if start:
            collector.start()
            deadline=time.time()+2
            while collector.latest_id is None and time.time()<deadline: time.sleep(.01)
        try: yield collector, Toolset(collector), store
        finally: collector.stop(); store.close()


class CollectorTests(unittest.TestCase):
    def test_failure_does_not_replace_last_good_data(self):
        with fixture() as (c, t, s):
            previous = s.latest_success()['id']
            c.set_scenario('timeout'); c.read_once()
            state=c.status()
            self.assertEqual(state['quality'], 'error')
            self.assertEqual(state['last_success']['id'], previous)
            self.assertEqual(state['consecutive_successes'],0)

    def test_old_samples_are_not_fresh_after_restart(self):
        with fixture(start=False) as (c,t,s):
            s.sample('simulation',True,{'temperature':25,'humidity':50})
            c.thread=type('Alive',(),{'is_alive':lambda self: True,'join':lambda self,timeout:None})()
            self.assertEqual(c.status()['quality'],'stale')

    def test_stale_age_is_enforced(self):
        with fixture(start=False) as (c,t,s):
            c.read_once()
            c.thread=type('Alive',(),{'is_alive':lambda self:True,'join':lambda self,timeout:None})()
            with patch('diagnosis.acquisition.time.time', return_value=time.time()+20):
                self.assertEqual(c.status()['quality'],'stale')

    def test_stopped_collector_not_recovered_by_probe(self):
        with fixture() as (c,t,s):
            c.set_scenario('collector_stopped')
            result=t.execute('retest',{})
            self.assertTrue(result['all_reads_valid'])
            self.assertFalse(result['recovery_confirmed'])

    def test_recovery_requires_three_valid_reads(self):
        with fixture() as (c,t,s):
            c.set_scenario('timeout'); c.read_once()
            self.assertFalse(t.execute('retest',{})['recovery_confirmed'])
            c.set_scenario('normal')
            result=t.execute('retest',{})
            self.assertTrue(result['recovery_confirmed'])
            self.assertEqual(len({r['sample_id'] for r in result['attempts']}),3)

    def test_simulation_truth_not_in_tool_results(self):
        with fixture() as (c,t,s):
            c.set_scenario('timeout');c.read_once()
            result=[t.execute('collector_status',{}),t.execute('recent_samples',{'limit':5}),t.execute('compare_config',{})]
            serialized=json.dumps(result)
            self.assertNotIn('scenario',serialized)
            self.assertNotIn('simulation_scenario',serialized)

    def test_tool_validation(self):
        with fixture() as (c,t,s):
            for name,args in [('run_shell',{}),('recent_samples',{'limit':True}),
                              ('recent_samples',{'limit':500}),('list_ports',{'extra':1}),
                              ('search_manual',{'query':''})]:
                with self.subTest(name=name,args=args),self.assertRaises(ValueError):t.execute(name,args)

    def test_live_mode_requires_explicit_hardware_profile(self):
        with self.assertRaises(ValueError): SerialBackend(Profile())

    def test_live_config_needs_independent_reference(self):
        with fixture(start=False) as (c,t,s):
            live = SerialBackend.__new__(SerialBackend)
            live.profile = c.profile
            collector = Collector(c.profile, live, s)
            result = Toolset(collector).execute('compare_config', {})
            self.assertFalse(result['comparison_available'])
            self.assertIsNone(result['reference'])
            collector.reference_profile = replace(c.profile, baudrate=19200)
            result = Toolset(collector).execute('compare_config', {})
            self.assertTrue(result['comparison_available'])
            self.assertEqual(result['differences'][0]['field'], 'baudrate')

    def test_probe_rejects_insufficient_budget_without_reads(self):
        with fixture(start=False) as (c,t,s):
            with self.assertRaises(RuntimeError):
                t.execute('retest', {}, deadline=time.monotonic()+.05)
            self.assertEqual(s.samples(10), [])

    def test_probe_wait_does_not_block_status(self):
        with fixture() as (c,t,s):
            worker = threading.Thread(target=lambda: t.execute('retest', {}))
            worker.start()
            time.sleep(.1)
            started = time.monotonic()
            c.status()
            self.assertLess(time.monotonic()-started, .2)
            worker.join(3)
            self.assertFalse(worker.is_alive())

    def test_interleaved_background_failure_prevents_recovery(self):
        with fixture(start=False) as (c,t,s):
            c.thread=type('Alive',(),{'is_alive':lambda self:True,'join':lambda self,timeout:None})()
            def wait_with_background_failure(interval):
                c.backend.scenario='timeout';c.read_once()
                c.backend.scenario='normal'
                return False
            with patch.object(c.stop_event,'wait',side_effect=wait_with_background_failure):
                result=t.execute('retest',{})
            self.assertTrue(result['all_reads_valid'])
            self.assertFalse(result['window_without_failures'])
            self.assertFalse(result['recovery_confirmed'])


class AgentTests(unittest.TestCase):
    def test_model_recovery_words_never_become_host_observations(self):
        class Hallucination:
            kind='test_script_not_llm'
            def complete(self,messages,tools,timeout=45):
                return {'content':json.dumps({'summary':'已经恢复','findings':[{'text':'三次成功','evidence_ids':['E1']}],'hypotheses':[],'next_steps':[]})},{}
        with fixture() as (c,t,s):
            c.set_scenario('timeout');c.read_once()
            r=Agent(t,s,Hallucination()).run('确认恢复')
            self.assertEqual(r['status'],'completed')
            self.assertFalse(r['interpretation_verified'])
            self.assertFalse(r['recovery_confirmed'])
            self.assertIn('timeout',r['observations'][0]['text'])
            self.assertNotIn('三次成功',json.dumps(r['observations'],ensure_ascii=False))

    def test_time_budget_stops_before_model_call(self):
        with fixture() as (c,t,s):
            r=Agent(t,s,max_seconds=0).run('检查')
            self.assertEqual(r['status'],'failed')
            self.assertEqual(r['trace'],[])

    def test_baseline_locates_missing_port(self):
        with fixture() as (c,t,s):
            c.set_scenario('usb_missing');c.read_once()
            result=Agent(t,s).run('数据没有更新')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['provider'],'rule_baseline')
            self.assertIn('串口',result['report']['summary'])
            self.assertFalse(result['recovery_confirmed'])
            self.assertEqual(len(s.sessions()),1)

    def test_baseline_does_not_claim_timeout_root_cause(self):
        with fixture() as (c,t,s):
            c.set_scenario('timeout');c.read_once()
            result=Agent(t,s).run('是不是断电？')
            self.assertIn('根因尚未确定',result['report']['summary'])
            self.assertFalse(result['recovery_confirmed'])

    def test_baseline_checks_parameter_evidence(self):
        with fixture() as (c,t,s):
            c.set_scenario('parameter_mismatch');c.read_once()
            result=Agent(t,s).run('检查参数')
            self.assertIn('不一致',result['report']['summary'])
            self.assertFalse(result['recovery_confirmed'])

    def test_scripted_provider_executes_real_tool_then_finishes(self):
        class Scripted:
            kind='test_script_not_llm'
            def __init__(self):self.calls=0
            def complete(self,messages,tools,timeout=45):
                self.calls+=1
                if self.calls==1:return {'tool_calls':[{'function':{'name':'list_ports','arguments':{}}}]},{}
                assert messages[-1]['role']=='tool'
                return {'content':json.dumps({'summary':'已枚举串口','findings':[{'text':'取得串口列表','evidence_ids':['E2']}],'hypotheses':[],'next_steps':[]})},{}
        with fixture() as (c,t,s):
            result=Agent(t,s,Scripted()).run('检查串口')
            self.assertEqual(result['status'],'completed')
            self.assertEqual(result['trace'][1]['tool'],'list_ports')

    def test_invalid_model_evidence_fails_explicitly(self):
        class BadProvider:
            kind='test_script_not_llm'
            def complete(self,messages,tools,timeout=45):
                return {'content':json.dumps({'summary':'假结论','findings':[{'text':'假证据','evidence_ids':['E999']}],'hypotheses':[],'next_steps':[]})},{}
        with fixture() as (c,t,s):
            result=Agent(t,s,BadProvider()).run('检查')
            self.assertEqual(result['status'],'failed')
            self.assertIsNone(result['report'])

    def test_model_tool_loop_is_bounded(self):
        class Loop:
            kind='test_script_not_llm'
            def complete(self,messages,tools,timeout=45):return {'tool_calls':[{'function':{'name':'list_ports','arguments':{}}}]},{}
        with fixture() as (c,t,s):
            result=Agent(t,s,Loop(),max_rounds=2).run('检查')
            self.assertEqual(result['status'],'failed')
            self.assertEqual(len(result['trace']),3)

    def test_remote_provider_rejected(self):
        for url in ['https://example.com','http://127.0.0.1.evil.test','http://u:p@localhost:11434','http://localhost:11434/path']:
            with self.subTest(url=url),self.assertRaises(ValueError):OllamaProvider('test',url)

    def test_unavailable_provider_has_no_silent_baseline(self):
        class Unavailable:
            kind='ollama'
            def complete(self,messages,tools,timeout=45):raise RuntimeError('模型不可用')
        with fixture() as (c,t,s):
            result=Agent(t,s,Unavailable()).run('检查')
            self.assertEqual(result['status'],'failed')
            self.assertIsNone(result['report'])


class HttpTests(unittest.TestCase):
    def test_http_state_job_and_origin_boundary(self):
        with fixture() as (c,t,s):
            app=Application(c,Agent(t,s));server=create_server(app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            def post(path,body,origin=None):
                headers={'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                req=urllib.request.Request(url+path,json.dumps(body).encode(),headers)
                with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
            try:
                with urllib.request.urlopen(url+'/api/state') as r:self.assertEqual(json.load(r)['sensor']['source'],'simulation')
                with self.assertRaises(urllib.error.HTTPError) as error:post('/api/scenario',{'scenario':'normal'},'https://evil.invalid')
                self.assertEqual(error.exception.code,403)
                post('/api/scenario',{'scenario':'usb_missing'})
                job=post('/api/diagnose',{'question':'检查串口'})['job_id']
                deadline=time.time()+5
                while time.time()<deadline:
                    with urllib.request.urlopen(url+'/api/jobs/'+job) as r:result=json.load(r)
                    if result['status'] in ['completed','failed']:break
                    time.sleep(.02)
                self.assertEqual(result['status'],'completed')
                with urllib.request.urlopen(url+'/') as r:self.assertIn('工业采集诊断台',r.read().decode())
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+'/../README.md')
            finally:
                server.shutdown();server.server_close();thread.join();app.pool.shutdown(wait=True)


if __name__ == '__main__':unittest.main()
