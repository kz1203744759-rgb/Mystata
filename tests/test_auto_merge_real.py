"""Optional full chat-to-Stata integration using synthetic data only."""
import json
import os
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


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires local Stata')
class AutoMergeRealTest(unittest.TestCase):
    def test_chat_previews_executes_and_mounts(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            arguments=None
            def __init__(self,*args,**kwargs):pass
            async def start(self,*args):return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='preview_merge',arguments=json.dumps(Session.arguments),call_id='call')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    files=[('files',('left.csv',b'code,year,sales\n000001,2020,12\n000002,2021,\n000003,2021,3\n','text/csv')),
                           ('files',('right.csv',b'code,year,cost\n1,2020,4\n2,2021,9\n4,2021,8\n','text/csv'))]
                    upload=client.post('/api/raw-files',headers=headers,files=files)
                    self.assertEqual(upload.status_code,200,upload.text)
                    a,b=[v['id'] for v in upload.json()['added']]
                    source=lambda *pairs:[{'file_id':fid,'column_index':index} for fid,index in pairs]
                    Session.arguments={'file_ids':[a,b],'keys':['id','year'],'cardinality':'1:1','mappings':[
                        {'target':'id','role':'security_code','sources':source((a,0),(b,0))},
                        {'target':'year','role':'year','sources':source((a,1),(b,1))},
                        {'target':'sales','role':'other','sources':source((a,2))},
                        {'target':'cost','role':'other','sources':source((b,2))}]}
                    response=client.post('/api/chat',headers=headers,json={'message':'以 id 和 year 合并两个文件并挂载','selected_file_ids':[a,b]})
                    self.assertEqual(response.status_code,200,response.text)
                    payload=response.json()
                    self.assertTrue(payload['loaded'])
                    self.assertEqual(payload['dataset']['observations'],1)
                    self.assertEqual([e['tool'] for e in payload['events']],['preview_merge','etl'])
                    self.assertIn('合并已完成并挂载',payload['answer'])
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],payload['dataset'])
                    check=client.portal.call(app.worker.call,'stata_run',{'code':'display "CHECK_N=" _N','max_output_lines':100})
                    self.assertIn('CHECK_N=1',app.envelope_of(check)['data']['stdout'])
            finally:
                for p in reversed(patches):p.stop()
