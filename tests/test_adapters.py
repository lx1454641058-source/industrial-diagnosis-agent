"""Original adapter contract tests; fake serial and model endpoints are not hardware/LLM evidence."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import threading
from types import SimpleNamespace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from diagnosis.acquisition import SerialBackend, Collector, DemoBackend
from diagnosis.storage import Store
from diagnosis.agent import OllamaProvider
from diagnosis.protocol import Profile, AcquisitionError, parse_response


@unittest.skipUnless(importlib.util.find_spec('serial'), 'pyserial optional dependency not installed')
class SerialAdapterTests(unittest.TestCase):
    def setUp(self):
        self.profile=Profile(port='TEST_ONLY',hardware_confirmed=True,temperature_offset=1,humidity_offset=0)
        self.backend=SerialBackend(self.profile)

    def test_serial_adapter_writes_only_read_request_and_decodes_vendor_response(self):
        class Port:
            def __init__(self):self.buffer=bytes.fromhex('01 03 04 01 D7 00 D6 CA 69');self.written=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def reset_input_buffer(self):pass
            def write(self,data):self.written.append(data)
            def flush(self):pass
            def read(self,n):r,self.buffer=self.buffer[:n],self.buffer[n:];return r
        port=Port()
        with patch.object(self.backend,'ports',return_value=[{'device':'TEST_ONLY'}]),patch.object(self.backend.serial,'Serial',return_value=port) as serial:
            frame=self.backend.transact()
        self.assertEqual(port.written,[bytes.fromhex('01 03 00 00 00 02 C4 0B')])
        self.assertEqual(parse_response(frame,self.profile)['temperature'],21.4)
        self.assertEqual(serial.call_args.kwargs['write_timeout'],self.profile.timeout)

    def test_missing_port_never_opens_another_port(self):
        with patch.object(self.backend,'ports',return_value=[{'device':'COM_BLUETOOTH'}]),patch.object(self.backend.serial,'Serial') as serial:
            with self.assertRaises(AcquisitionError) as error:self.backend.transact()
        self.assertEqual(error.exception.code,'port_missing')
        serial.assert_not_called()

    def test_serial_open_error_is_reported_without_raw_exception(self):
        with patch.object(self.backend,'ports',return_value=[{'device':'TEST_ONLY'}]),patch.object(self.backend.serial,'Serial',side_effect=self.backend.serial.SerialException('private low-level details')):
            with self.assertRaises(AcquisitionError) as error:self.backend.transact()
        self.assertEqual(error.exception.code,'serial_error')
        self.assertNotIn('private',str(error.exception))

    def test_enumeration_os_error_is_recorded_and_collector_recovers(self):
        profile=replace(self.profile, interval=.5, stale_after=2)
        self.backend.profile=profile
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'test.sqlite3')
            collector=Collector(profile,self.backend,store)
            try:
                with patch.object(self.backend.serial.tools.list_ports,'comports',side_effect=OSError('private registry error')):
                    collector.start()
                    deadline=time.monotonic()+2
                    while collector.latest_id is None and time.monotonic()<deadline:time.sleep(.01)
                    self.assertTrue(collector.thread.is_alive())
                    self.assertEqual(collector.last_error,'enumeration_error')
                    self.assertNotIn('private',store.samples(1)[0]['detail'])
                    with patch.object(self.backend,'transact',side_effect=DemoBackend(profile).transact):
                        deadline=time.monotonic()+2
                        while collector.last_error and time.monotonic()<deadline:time.sleep(.01)
                        self.assertIsNone(collector.last_error)
                        self.assertEqual(collector.status()['quality'],'fresh')
            finally:collector.stop();store.close()


class OllamaWireTests(unittest.TestCase):
    def test_actual_http_adapter_sends_non_streaming_tools_and_returns_usage(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                body=json.dumps({'message':{'role':'assistant','tool_calls':[{'function':{'name':'list_ports','arguments':{}}}]},'eval_count':12}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            provider=OllamaProvider('script-fixture',f'http://127.0.0.1:{server.server_port}')
            message,usage=provider.complete([{'role':'user','content':'测试'}],[{'type':'function'}])
            self.assertEqual(received[0][0],'/api/chat')
            self.assertFalse(received[0][1]['stream'])
            self.assertEqual(received[0][1]['tools'],[{'type':'function'}])
            self.assertEqual(message['tool_calls'][0]['function']['name'],'list_ports')
            self.assertEqual(usage['eval_count'],12)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
