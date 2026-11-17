"""Opt-in Stata integration, using only temporary synthetic files."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
import app


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires local Stata')
class RealYearFilter(unittest.TestCase):
    def test_preview_and_execution_apply_inclusive_years(self):
        class Client:
            def __init__(self,**kwargs): pass
            async def close(self): pass
        class Session:
            arguments=None
            def __init__(self,*args,**kwargs): pass
            async def start(self,*args):
                return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='preview_merge',arguments=json.dumps(Session.arguments),call_id='call')])
            def completed_history(self):return []
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root) as temp:
            tmp=Path(temp).resolve()
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'),patch.object(app,'CONTEXT_DB',tmp/'context.sqlite'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for item in patches:item.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    left=b'code,year,sales\n1,2009,1\n2,2010,2\n3,2024,3\n4,2025,4\n'
                    right=b'code,year,cost\n1,2009,5\n2,2010,6\n3,2024,7\n4,2025,8\n'
                    response=client.post('/api/raw-files',headers=headers,files=[('files',('left.csv',left,'text/csv')),('files',('right.csv',right,'text/csv'))])
                    self.assertEqual(response.status_code,200,response.text)
                    a,b=[item['id'] for item in response.json()['added']]
                    Session.arguments={'file_ids':[a,b],'keys':['id','year'],'cardinality':'1:1','mappings':[
                        {'target':'id','role':'security_code','sources':[{'file_id':a,'column_index':0},{'file_id':b,'column_index':0}]},
                        {'target':'year','role':'year','sources':[{'file_id':a,'column_index':1},{'file_id':b,'column_index':1}]}]}
                    result=client.post('/api/chat',headers=headers,json={'message':'以 id 和 year 合并，保留2010-2024年数据','selected_file_ids':[a,b]})
                    self.assertEqual(result.status_code,200,result.text)
                    payload=result.json();self.assertTrue(payload['loaded']);self.assertEqual(payload['dataset']['observations'],2)
                    preview=payload['events'][0]['preview'];self.assertEqual(preview['metrics']['YEAR_FILTER_DROPPED'],2)
                    self.assertEqual(preview['metrics']['FINAL_ROWS'],2)
                    self.assertIn('2010—2024',payload['answer'])
                    result=client.portal.call(app.worker.call,'stata_run',{'code':'quietly count if year < 2010 | year > 2024\ndisplay "OUT_OF_RANGE=" r(N)','max_output_lines':100})
                    self.assertIn('OUT_OF_RANGE=0',app.envelope_of(result)['data']['stdout'])
            finally:
                for item in reversed(patches):item.stop()
