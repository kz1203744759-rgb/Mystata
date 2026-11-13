import sys
import unittest
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from merge_planner import build_preview_plan
import app


class MergePreviewTest(unittest.TestCase):
    def setUp(self):
        self.files={'a':{'filename':'a.dta','variables':[{'name':x} for x in ('stkcd','year','name','value')]},
                    'b':{'filename':'b.dta','variables':[{'name':x} for x in ('stock_code','year','company_name','cost')]}}
        def sources(*pairs): return [{'file_id':f,'column_index':i} for f,i in pairs]
        self.args={'file_ids':['a','b'],'keys':['id'],'cardinality':'1:1','mappings':[
            {'target':'id','role':'security_code','sources':sources(('a',0),('b',0))},
            {'target':'year','role':'year','sources':sources(('a',1),('b',1))},
            {'target':'name','role':'company_name','sources':sources(('a',2),('b',2))},
            {'target':'value','role':'other','sources':sources(('a',3))},
            {'target':'cost','role':'other','sources':sources(('b',3))}]}

    def test_id_only_and_composite_keys(self):
        plan=build_preview_plan(self.files,self.args)
        self.assertEqual(plan['keys'],['id'])
        self.assertEqual((plan['sample_retention'],plan['drop_all_missing'],plan['cardinality']),('matched',True,'1:1'))
        self.assertEqual([m['normalize'] for m in plan['mappings']],['stock','year','none','none','none'])
        self.assertFalse(plan['mappings'][2]['keep'])
        self.assertTrue(all(m['convert']=='none' for m in plan['mappings']))
        self.args['keys']=['id','year']
        self.assertEqual(build_preview_plan(self.files,self.args)['keys'],['id','year'])

    def test_rejects_unmapped_fields_and_unknown_key(self):
        self.args['mappings'].pop()
        with self.assertRaisesRegex(ValueError,'映射不完整'):
            build_preview_plan(self.files,self.args)
        self.args['keys']=['wrong']
        with self.assertRaises(ValueError):
            build_preview_plan(self.files,self.args)

    def test_rejects_mislabelled_security_code(self):
        self.args['mappings'][0]['role']='other'
        with self.assertRaisesRegex(ValueError,'证券代码'):
            build_preview_plan(self.files,self.args)

    def test_agent_hands_off_preview_without_exposing_log(self):
        class Client:
            def __init__(self,**kwargs): pass
            async def close(self): pass
        class Session:
            output=None
            def __init__(self,*args,**kwargs): pass
            async def start(self,instruction,message):
                return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='preview_merge',arguments=json.dumps(self_args),call_id='c1')])
            async def resume(self,response,outputs):
                Session.output=json.loads(outputs[0]['output'])
                return SimpleNamespace(id='two',status='completed',text='预检完成，请确认。',calls=[])
            def completed_history(self): return []
        self_args=self.args
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); stata=root/'stata.exe'; stata.touch()
            for item in self.files.values():
                item.update(path=str(root/item['filename']),format='dta',observations=2)
            preview={'ok':True,'metrics':{'FINAL_ROWS':1},'output':'PRIVATE_LOCAL_LOG','error':''}
            with patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value=self.files),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app.shutil,'which',return_value='uv'),patch.object(app,'preview_plan',new=AsyncMock(return_value=preview)):
                app.settings.update(api_key='fake-key',model='fake-model',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'请以 id 合并预检','selected_file_ids':['a','b']})
                self.assertEqual(response.status_code,200,response.text)
                event=response.json()['events'][0]
                self.assertEqual(event['plan']['keys'],['id'])
                self.assertEqual(event['preview']['log'],'PRIVATE_LOCAL_LOG')
                self.assertIn('尚未正式合并或挂载',response.json()['answer'])
                self.assertNotIn('PRIVATE_LOCAL_LOG',response.json()['answer'])
                self.assertFalse(response.json()['loaded'])

    def test_merge_runs_after_successful_preview_and_mounts(self):
        class Client:
            def __init__(self,**kwargs): pass
            async def close(self): pass
        args=self.args
        class Session:
            def __init__(self,*args,**kwargs): pass
            async def start(self,*unused): return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='preview_merge',arguments=json.dumps(args),call_id='c1')])
            def completed_history(self): return []
        async def execute(plan,files,record):
            self.assertFalse(record)
            dataset={'filename':'result.dta','observations':1,'variables':[{'name':'id'}]}
            app.workspace.update(dataset=dataset,path='result',loaded=True)
            return {'dataset':dataset,'event':{'tool':'etl','label':'数据清洗整合','error':False},'artifacts':[{'name':'result.dta'}]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stata=root/'stata.exe';stata.touch()
            for item in self.files.values(): item.update(path=str(root/item['filename']),format='dta',observations=2)
            preview={'ok':True,'metrics':{'FINAL_ROWS':1},'output':'','error':''}
            with patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value=self.files),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app.shutil,'which',return_value='uv'),patch.object(app,'preview_plan',new=AsyncMock(return_value=preview)),patch.object(app,'execute_etl',side_effect=execute) as run:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                response=TestClient(app.app,base_url='http://127.0.0.1:8765').post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'以 id 合并这些文件并挂载','selected_file_ids':['a','b']})
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(response.json()['loaded'])
                self.assertIn('已完成并挂载',response.json()['answer'])
                self.assertEqual([event['tool'] for event in response.json()['events']],['preview_merge','etl'])
                self.assertEqual(len(app.workspace['events']),2)
                self.assertEqual(len(response.json()['artifacts']),1)
                run.assert_awaited_once()

    def test_failed_preview_does_not_run_or_replace_active_dataset(self):
        class Client:
            def __init__(self,**kwargs): pass
            async def close(self): pass
        args=self.args
        class Session:
            def __init__(self,*args,**kwargs): pass
            async def start(self,*unused): return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='preview_merge',arguments=json.dumps(args),call_id='c1')])
            def completed_history(self): return []
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stata=root/'stata.exe';stata.touch()
            for item in self.files.values():item.update(path=str(root/item['filename']),format='dta',observations=2)
            preview={'ok':False,'metrics':{'SOURCE_1_DUPLICATE_ROWS':2},'output':'duplicate','error':'r(459)'}
            with patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value=self.files),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app.shutil,'which',return_value='uv'),patch.object(app,'preview_plan',new=AsyncMock(return_value=preview)),patch.object(app,'execute_etl',new=AsyncMock()) as run:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                dataset={'filename':'previous.dta','observations':2,'variables':[]}
                app.workspace.update(dataset=dataset,path='existing',messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=True)
                response=TestClient(app.app,base_url='http://127.0.0.1:8765').post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'以 id 合并文件并挂载','selected_file_ids':['a','b']})
                self.assertEqual(response.status_code,200,response.text)
                self.assertIn('预检未通过',response.json()['answer'])
                self.assertEqual(response.json()['dataset'],dataset)
                run.assert_not_awaited()

