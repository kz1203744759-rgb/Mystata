import sys
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app
from etl_engine import compile_plan, validate_plan


class EtlValidationTest(unittest.TestCase):
    def setUp(self):
        self.files={'a':{'filename':'a.csv','path':'/tmp/a.csv','variables':[{'name':'id'},{'name':'value'}]},
                    'b':{'filename':'b.csv','path':'/tmp/b.csv','variables':[{'name':'code'},{'name':'value'}]}}
        self.rows=[{'target':'id','sources':{'a':0,'b':0},'convert':'none','keep':True},
                   {'target':'value','sources':{'a':1,'b':1},'convert':'numeric','keep':True}]
        self.plan={'file_ids':['a','b'],'mode':'merge','cardinality':'1:1','keys':['id'],'mappings':self.rows}

    def test_compiles_conflict_checked_merge_and_append(self):
        code,frame=compile_plan(self.plan,self.files,Path('/tmp/run'),Path('/tmp/run/active.dta'),'a'*32)
        self.assertIn('merge 1:1 id',code)
        self.assertIn('update generate(',code)
        self.assertIn('assert eaaaaaaaaaa_m1 != 5',code)
        self.assertIn('stringcols(_all)',code)
        self.assertEqual(frame,'etlf'+'a'*12)
        code,_=compile_plan({**self.plan,'mode':'append','keys':[]},self.files,Path('/tmp/run'),Path('/tmp/run/active.dta'),'b'*32)
        self.assertIn('append using',code)

    def test_rejects_invalid_names_missing_keys_and_duplicate_sources(self):
        for bad in ['bad name','x;drop','1abc','_merge']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_plan({**self.plan,'mappings':[{**self.rows[0],'target':bad},self.rows[1]]},self.files)
        with self.assertRaises(ValueError): validate_plan({**self.plan,'keys':['missing']},self.files)
        with self.assertRaises(ValueError): validate_plan({**self.plan,'mappings':self.rows+[{'target':'again','sources':{'a':0},'convert':'none','keep':True}]},self.files)

    def test_year_filter_is_identical_in_preview_and_execution(self):
        plan={**self.plan,'year_filter':{'field':'value','start':2010,'end':2024}}
        for preview in (True,False):
            code,_=compile_plan(plan,self.files,Path('/tmp/run'),Path('/tmp/run/result.dta'),'a'*32,preview=preview)
            self.assertIn('drop if missing(value) | value < 2010 | value > 2024',code)
            self.assertIn('ETL_YEAR_FILTER_DROPPED=',code)
            self.assertIn('assert value >= 2010',code)
            self.assertIn('assert value <= 2024',code)
        for bad in ({'field':'missing','start':2010,'end':2024},{'field':'value','start':2025,'end':2024},
                    {'field':'value','start':None,'end':None},{'field':'value','start':True,'end':2024}):
            with self.assertRaises(ValueError):validate_plan({**self.plan,'year_filter':bad},self.files)

    def test_raw_upload_keeps_existing_active_dataset(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp)
            with patch.object(app,'RAW',root/'raw'),patch.object(app,'RAW_MANIFEST',root/'raw'/'manifest.json'):
                original={'filename':'active.dta','variables':[]}
                app.workspace.update(dataset=original,loaded=True,messages=[{'role':'user','content':'keep'}])
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                headers={'Origin':'http://127.0.0.1:8765'}
                response=client.post('/api/raw-files',headers=headers,files=[('files',('one.csv',b'id\n001\n','text/csv')),('files',('two.csv',b'id\n002\n','text/csv'))])
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(len(response.json()['added']),2)
                self.assertEqual(response.json()['added'][0]['preview'][0][0],'001')
                state=client.get('/api/workspace').json()
                self.assertEqual(state['dataset'],original)
                self.assertTrue(state['loaded'])
                self.assertEqual(state['messages'][0]['content'],'keep')
                self.assertEqual(len(state['raw_files']),2)

    def test_ai_suggestion_only_sends_metadata_and_does_not_run_stata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp)
            class FakeModel:
                async def create(self, **kwargs):
                    user=kwargs['messages'][-1]['content']
                    self_outer.assertNotIn('PRIVATE_VALUE_123',user)
                    self_outer.assertIn('first.csv',user)
                    files=__import__('json').loads(user)
                    a,b=[f['id'] for f in files]
                    suggestion={'mappings':[{'target':'id','sources':{a:0,b:0},'convert':'none','keep':True}], 'keys':['id']}
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=__import__('json').dumps(suggestion)))])
            class FakeClient:
                def __init__(self,**kwargs): self.chat=SimpleNamespace(completions=FakeModel())
                async def close(self): pass
            self_outer=self
            with patch.object(app,'RAW',root/'raw'),patch.object(app,'RAW_MANIFEST',root/'raw'/'manifest.json'),patch.object(app,'AsyncOpenAI',FakeClient):
                app.settings.update(api_key='fake',model='model',provider='deepseek',base_url='https://api.deepseek.com')
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                headers={'Origin':'http://127.0.0.1:8765'}
                uploaded=client.post('/api/raw-files',headers=headers,files=[('files',('first.csv',b'id\nPRIVATE_VALUE_123\n','text/csv')),('files',('second.csv',b'id\nXYZ\n','text/csv'))])
                ids=[f['id'] for f in uploaded.json()['added']]
                with patch.object(app.worker,'call',side_effect=AssertionError('Stata should not run')):
                    result=client.post('/api/etl/suggest',headers=headers,json={'file_ids':ids})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['keys'],['id'])

    def test_upgrade_snapshot_restores_visible_history_without_credentials(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            runs=Path(tmp)
            snapshot=runs/'upgrade.json'
            snapshot.write_text(json.dumps({'dataset':None,'messages':[{'role':'user','content':'past'}],'events':[],'artifacts':[]}),encoding='utf-8')
            with patch.object(app,'RUNS',runs),patch.dict(os.environ,{'ECONAGENT_SESSION_RESTORE':str(snapshot)}):
                app.workspace.update(messages=[],events=[],artifacts=[])
                app.restore_visible_session()
                self.assertEqual(app.workspace['messages'][0]['content'],'past')
                self.assertIn('上下文已重置',app.workspace['messages'][1]['content'])
                self.assertFalse(snapshot.exists())

if __name__=='__main__': unittest.main()
