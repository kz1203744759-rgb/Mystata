import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


def tool_call(code,index):
    return SimpleNamespace(name='run_stata',arguments=json.dumps({'code':code}),call_id=f'call-{index}')


def pending(code,index):
    return SimpleNamespace(id=f'r{index}',status='tool_calls',text='',calls=[tool_call(code,index)])


def done(text):
    return SimpleNamespace(id='last',status='completed',text=text,calls=[])


class FakeResult:
    isError=False
    def __init__(self,success=True,log_path=None):
        self.structuredContent={'result':{'success':success,'data':{'stdout':'result'},'error':None if success else {'message':'failed','rc':601},'log':{'path':str(log_path)} if log_path else {}}}
    def model_dump(self,**_): return {'structuredContent':self.structuredContent,'isError':False}


class FakeWorker:
    def __init__(self,success=True):self.success=success;self.scripts=[];self.log_path=None
    async def call(self,name,args):
        assert name=='stata_run'
        self.scripts.append(Path(args['code']).read_text(encoding='utf-8'))
        return FakeResult(self.success,self.log_path)


class FakeClient:
    def __init__(self,**_):pass
    async def close(self):pass


class FakeSession:
    responses=[]
    outputs=[]
    instruction=''
    def __init__(self,*_,**__): self.index=0
    async def start(self,instruction,message):
        FakeSession.instruction=instruction
        return FakeSession.responses[0]
    async def resume(self,response,outputs):
        FakeSession.outputs.append(outputs)
        self.index+=1
        return FakeSession.responses[self.index]
    def completed_history(self):return []


class AgentRoundsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        root=Path(self.tmp.name)
        stata=root/'stata.exe';stata.touch()
        self.worker=FakeWorker()
        self.raw={'file_a':{'filename':'ROE.dta','path':str(root/'9c123.dta'),'format':'dta','observations':1,'variables':[]}}
        self.patches=[patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),
                      patch.object(app,'worker',self.worker),patch.object(app,'read_raw',return_value=self.raw),
                      patch.object(app,'AsyncOpenAI',FakeClient),patch.object(app,'ModelSession',FakeSession),
                      patch.object(app.shutil,'which',return_value='uv')]
        for p in self.patches:p.start()
        app.settings.update(api_key='fake-key',model='fake-model',provider='deepseek',base_url='https://example.test')
        app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
        FakeSession.outputs=[]
        self.client=TestClient(app.app,base_url='http://127.0.0.1:8765')

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def request(self):
        return self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},
            json={'message':'检查 ROE 并处理','selected_file_ids':['file_a']})

    def test_final_response_after_twelfth_round_is_preserved(self):
        FakeSession.responses=[pending(f'display {i}',i) for i in range(12)]+[done('检查完成。')]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['answer'],'检查完成。')
        self.assertEqual(len(self.worker.scripts),12)
        self.assertEqual(len(result.json()['events']),12)

    def test_limit_summarizes_without_executing_additional_call(self):
        FakeSession.responses=[pending(f'display {i}',i) for i in range(13)]+[done('已检查，合并未执行。')]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn('合并未执行',result.json()['answer'])
        self.assertIn('达到工具调用上限',result.json()['answer'])
        self.assertEqual(len(self.worker.scripts),12)
        self.assertIn('未执行该调用',FakeSession.outputs[-1][0]['output'])

    def test_limit_stops_if_model_requests_still_more_tools(self):
        FakeSession.responses=[pending(f'display {i}',i) for i in range(14)]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn('达到工具调用上限',result.json()['answer'])
        self.assertEqual(len(self.worker.scripts),12)
        self.assertIsNone(app.workspace['response_id'])
        self.assertEqual(app.workspace['chat_history'],[])

    def test_actual_raw_path_is_available_as_local_macro(self):
        FakeSession.responses=[pending("describe using `ea_raw_1'",0),done('已检查。')]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn('ROE.dta',FakeSession.instruction)
        self.assertIn('ea_raw_1',FakeSession.instruction)
        self.assertIn(f'local ea_raw_1 "{Path(self.raw["file_a"]["path"]).as_posix()}"',self.worker.scripts[0])
        self.assertIn("describe using `ea_raw_1'",self.worker.scripts[0])
        event=result.json()['events'][0]
        self.assertIn('原始文件：ROE.dta',event['readable_code'])
        self.assertIn("describe using `ea_raw_1'",event['readable_code'])
        self.assertTrue(any(item['name'].endswith('-readable.do') for item in result.json()['artifacts']))

    def test_identical_failed_code_is_not_executed_twice(self):
        self.worker.success=False
        FakeSession.responses=[pending('bad command',0),pending('bad command',1),done('需要调整检查代码。')]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(self.worker.scripts),1)
        self.assertEqual(len(result.json()['events']),2)
        self.assertIn('未重复执行',result.json()['events'][1]['output'])

    def test_full_log_is_provided_if_mcp_short_output_omits_result(self):
        log=Path(self.tmp.name)/'stata.log'
        log.write_text('. display "STATA_RESULT=42"\nSTATA_RESULT=42\n',encoding='utf-8')
        self.worker.log_path=log
        FakeSession.responses=[pending('display 42',0),done('已检查。')]
        result=self.request()
        self.assertEqual(result.status_code,200,result.text)
        actual=json.loads(FakeSession.outputs[0][0]['output'])
        self.assertIn('STATA_RESULT=42',actual['structuredContent']['result']['data']['stdout'])
        self.assertIn('STATA_RESULT=42',result.json()['events'][0]['output'])

    def test_large_log_remains_bounded_valid_json(self):
        encoded=app.tool_result_for_model({'success':True,'data':{}},'数'*80000,False)
        parsed=json.loads(encoded)
        self.assertLess(len(encoded),40000)
        self.assertIn('仅显示末尾',parsed['structuredContent']['result']['data']['stdout'])


if __name__=='__main__':unittest.main()
