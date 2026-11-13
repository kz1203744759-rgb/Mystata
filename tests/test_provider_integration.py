import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app


class FakeResult:
    isError = False
    structuredContent = {'result': {'success': True, 'data': {'stdout': 'N = 3'}}}
    def model_dump(self, **_): return {'structuredContent': self.structuredContent, 'isError': False}


class FakeWorker:
    async def call(self, name, args):
        assert name == 'stata_run'
        assert 'code' in args
        return FakeResult()
    async def stop(self): pass


class FakeResponses:
    async def create(self, **kwargs):
        assert kwargs['model'] == 'gpt-test'
        return SimpleNamespace(id='openai-id', status='completed', output_text='OpenAI OK', output=[])


class FakeChat:
    counter = 0
    async def create(self, **kwargs):
        assert kwargs['model'] == 'deepseek-flash'
        messages = kwargs['messages']
        assert any(tool['function']['name'] == 'run_stata' for tool in kwargs['tools'])
        FakeChat.counter += 1
        if FakeChat.counter == 1:
            function = SimpleNamespace(name='run_stata', arguments='{"code":"display 3"}')
            call = SimpleNamespace(id='tool-1', function=function)
            message = SimpleNamespace(content=None, reasoning_content='internal-state', tool_calls=[call])
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason='tool_calls')])
        assert any(m.get('reasoning_content') == 'internal-state' for m in messages)
        assert any(m.get('role') == 'tool' and m['tool_call_id'] == 'tool-1' for m in messages)
        if FakeChat.counter == 3:
            assert any(m.get('role') == 'assistant' and m.get('content') == 'DeepSeek first' for m in messages)
        content = 'DeepSeek first' if FakeChat.counter == 2 else 'DeepSeek follow-up'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, reasoning_content='next-state', tool_calls=None), finish_reason='stop')])


class FakeClient:
    seen = []
    def __init__(self, api_key, base_url):
        self.seen.append((api_key,base_url))
        self.responses = FakeResponses()
        self.chat = SimpleNamespace(completions=FakeChat())
    async def close(self): pass


class ProviderIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY':'','OPENAI_MODEL':'','DEEPSEEK_API_KEY':'','DEEPSEEK_MODEL':''})
        self.env.start()
        self.user_env_patch=patch.object(app,'windows_user_env',return_value='')
        self.user_env_patch.start()
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.run_patch = patch.object(app,'RUNS',Path(self.temp.name))
        self.client_patch = patch.object(app,'AsyncOpenAI',FakeClient)
        self.worker_patch = patch.object(app,'worker',FakeWorker())
        self.run_patch.start(); self.client_patch.start(); self.worker_patch.start()
        app.settings.update(api_key='',model='',provider='deepseek',base_url='https://api.deepseek.com')
        app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
        FakeChat.counter=0; FakeClient.seen=[]
        self.client=TestClient(app.app,base_url='http://127.0.0.1:8765')
        self.client.__enter__()
        self.headers={'Origin':'http://127.0.0.1:8765'}

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.worker_patch.stop(); self.client_patch.stop(); self.run_patch.stop()
        self.temp.cleanup(); self.user_env_patch.stop(); self.env.stop()

    def save(self, **options):
        return self.client.post('/api/settings',headers=self.headers,json=options)

    def test_deepseek_tools_and_followup(self):
        result=self.save(provider='deepseek',base_url='https://api.deepseek.com',api_key='fake-key',model='deepseek-flash')
        self.assertEqual(result.status_code,200)
        self.assertNotIn('fake-key',self.client.get('/api/status').text)
        first=self.client.post('/api/chat',headers=self.headers,json={'message':'run analysis'})
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['answer'],'DeepSeek first')
        self.assertEqual(first.json()['events'][0]['output'],'N = 3')
        second=self.client.post('/api/chat',headers=self.headers,json={'message':'continue'})
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['answer'],'DeepSeek follow-up')
        self.assertEqual(FakeClient.seen[-1],('fake-key','https://api.deepseek.com'))
        self.assertNotIn('internal-state',self.client.get('/api/workspace').text)

    def test_openai_native_and_key_isolation(self):
        self.save(provider='deepseek',base_url='https://api.deepseek.com',api_key='fake-key',model='deepseek-flash')
        self.assertEqual(self.save(provider='openai',base_url='https://api.openai.com/v1',api_key='',model='gpt-test').status_code,400)
        self.assertEqual(self.save(provider='openai',base_url='https://api.openai.com/v1',api_key='other-key',model='gpt-test').status_code,200)
        result=self.client.post('/api/chat',headers=self.headers,json={'message':'hello'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['answer'],'OpenAI OK')
        self.assertEqual(FakeClient.seen[-1],('other-key','https://api.openai.com/v1'))

    def test_endpoint_validation_and_origin(self):
        self.assertEqual(self.save(provider='custom',base_url='http://remote.example/v1',api_key='secret',model='m').status_code,400)
        self.assertEqual(self.save(provider='custom',base_url='https://remote.example/v1/chat/completions',api_key='secret',model='m').status_code,400)
        self.assertEqual(self.save(provider='custom',base_url='http://localhost:9000/v1',api_key='secret',model='m').status_code,200)
        result=self.client.post('/api/settings',headers={'Origin':'https://foreign.example'},json={'api_key':'x','model':'m'})
        self.assertEqual(result.status_code,403)

    def test_save_deepseek_key_to_user_environment_without_exposing_it(self):
        with patch.object(app,'persist_deepseek_user_settings') as save:
            result=self.save(provider='deepseek',base_url='https://api.deepseek.com',api_key='private-fake-key',model='deepseek-flash',remember_api_key=True)
            self.assertEqual(result.status_code,200,result.text)
            save.assert_called_once_with('private-fake-key','deepseek-flash')
            self.assertTrue(result.json()['remembered'])
            self.assertNotIn('private-fake-key',result.text)
            self.assertNotIn('private-fake-key',self.client.get('/api/status').text)

    def test_persist_rejects_custom_endpoint_and_missing_key(self):
        with patch.object(app,'persist_deepseek_user_settings') as save:
            result=self.save(provider='deepseek',base_url='https://example.test',api_key='secret',model='m',remember_api_key=True)
            self.assertEqual(result.status_code,400)
            result=self.save(provider='deepseek',base_url='https://api.deepseek.com',api_key='',model='m',remember_api_key=True)
            self.assertEqual(result.status_code,400)
            save.assert_not_called()

    def test_deepseek_environment_fallback_never_used_for_custom_endpoint(self):
        with patch.object(app,'windows_user_env',side_effect=lambda n:{'DEEPSEEK_API_KEY':'env-key','DEEPSEEK_MODEL':'env-model'}.get(n,'')):
            self.assertEqual(app.current_settings()['api_key'],'env-key')
            self.assertEqual(app.current_settings()['model'],'env-model')
            app.settings['base_url']='https://example.test'
            self.assertEqual(app.current_settings()['api_key'],'')
            self.assertEqual(app.current_settings()['model'],'')

    def test_saved_key_and_model_are_read_on_a_fresh_session(self):
        values={}
        class FakeKey:
            def __enter__(self):return self
            def __exit__(self,*args):pass
        def query(key,name):
            if name not in values:raise FileNotFoundError(name)
            return values[name]
        def set_value(key,name,reserved,kind,value):values[name]=(value,kind)
        registry=SimpleNamespace(HKEY_CURRENT_USER=1,KEY_QUERY_VALUE=1,KEY_SET_VALUE=2,KEY_READ=4,REG_SZ=1,REG_EXPAND_SZ=2,
            CreateKeyEx=lambda *args:FakeKey(),OpenKey=lambda *args:FakeKey(),QueryValueEx=query,SetValueEx=set_value,DeleteValue=lambda key,name:values.pop(name,None))
        with patch.dict(sys.modules,{'winreg':registry}),patch.object(app.sys,'platform','win32'),patch.object(app,'windows_user_env',side_effect=lambda name: values.get(name,('',))[0]):
            app.persist_deepseek_user_settings('test-key','custom-model')
            app.settings.update(api_key='',model='',provider='deepseek',base_url='https://api.deepseek.com')
            self.assertEqual(app.current_settings()['api_key'],'test-key')
            self.assertEqual(app.current_settings()['model'],'custom-model')

    def test_model_keys_are_not_passed_to_stata_worker(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-ds','OPENAI_API_KEY':'test-openai'}):
            worker_env=app.server_params().env
            self.assertNotIn('DEEPSEEK_API_KEY',worker_env)
            self.assertNotIn('OPENAI_API_KEY',worker_env)

    def test_unwritable_runs_reports_actionable_error(self):
        self.save(provider='deepseek',base_url='https://api.deepseek.com',api_key='fake-key',model='deepseek-flash')
        with patch.object(app.Path, 'mkdir', side_effect=PermissionError('denied')):
            result=self.client.post('/api/chat',headers=self.headers,json={'message':'run analysis'})
        self.assertEqual(result.status_code,500)
        self.assertIn('无法写入任务记录', result.json()['detail'])

if __name__ == '__main__': unittest.main()
