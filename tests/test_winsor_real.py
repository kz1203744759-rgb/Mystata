"""Optional real winsor2 tests using isolated synthetic data."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata and winsor2')
class WinsorRealTest(unittest.TestCase):
    def test_chat_registered_tool_runs_real_winsor2(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*args,**kwargs):pass
            async def start(self,*args):
                import json
                return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='winsor2_columns',arguments=json.dumps({'variables':['X'],'excluded_variables':[],'cut_kind':'symmetric','p1':5,'p2':0,'mode':'replace','suffix':'','scope':'all'}),call_id='call')])
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
                    source=tmp/'data.dta';pd.DataFrame({'x':list(range(1,101))}).to_stata(source,write_index=False)
                    upload=client.post('/api/raw-files',headers=headers,files=[('files',('data.dta',source.read_bytes(),'application/octet-stream'))])
                    fid=upload.json()['added'][0]['id']
                    self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    response=client.post('/api/chat',headers=headers,json={'message':'对x上下5%缩微不要新变量'})
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json()
                    self.assertTrue(result['loaded'])
                    self.assertIn('缩尾已完成',result['answer'])
                    self.assertNotIn('x_w',[v['name'] for v in result['dataset']['variables']])
                    self.assertEqual(result['events'][0]['winsor_report']['changed'][0]['source'],'x')
                    self.assertEqual(result['events'][0]['winsor_report']['changed'][0]['target'],'x')
                    self.assertEqual((result['events'][0]['winsor_report']['lower'],result['events'][0]['winsor_report']['upper']),(5.,95.))
                    self.assertEqual(result['events'][0]['tool'],'winsor2_columns')
                    self.assertTrue(any(a['name']=='winsor2-readable.do' for a in result['artifacts']))
            finally:
                for p in reversed(patches):p.stop()

    def test_new_replace_binary_rollback_and_readable_script(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json')]
            for p in patches:p.start()
            try:
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    source=tmp/'source.dta'
                    pd.DataFrame({'id':list(range(1,101)),'x':list(range(1,101)),'binary':[i%2 for i in range(100)]}).to_stata(source,write_index=False)
                    original=source.read_bytes()
                    upload=client.post('/api/raw-files',headers=headers,files=[('files',('source.dta',original,'application/octet-stream'))])
                    fid=upload.json()['added'][0]['id']
                    self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    spec={'variables':['x'],'lower':1,'upper':99,'mode':'new','suffix':'_w'}
                    result=client.post('/api/winsor2',headers=headers,json=spec)
                    self.assertEqual(result.status_code,200,result.text)
                    payload=result.json();self.assertEqual(payload['report']['changed'][0]['rows'],2)
                    self.assertEqual(payload['dataset']['observations'],100)
                    names=[v['name'] for v in payload['dataset']['variables']]
                    self.assertEqual(names,['id','x','binary','x_w'])
                    self.assertIn('winsor2 x, cuts(1 99) suffix(_w)',payload['event']['readable_code'])
                    artifact=next(a for a in payload['artifacts'] if a['name']=='winsor2-readable.do')
                    run=tmp/'runs'/artifact['url'].split('/')[3]
                    data=pd.read_stata(run/'active.dta',convert_categoricals=False)
                    self.assertEqual(data.loc[0,'x'],1)
                    self.assertAlmostEqual(data.loc[0,'x_w'],1.5)
                    self.assertAlmostEqual(data.loc[99,'x_w'],99.5)
                    prior=client.get('/api/workspace').json()['dataset']
                    failed=client.post('/api/winsor2',headers=headers,json={'variables':['binary'],'lower':1,'upper':99,'mode':'replace'})
                    self.assertEqual(failed.status_code,400,failed.text)
                    self.assertTrue(failed.json()['restored'])
                    self.assertIn('0/1',failed.json()['detail'])
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],prior)
                    self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    replay=client.portal.call(app.worker.call,'stata_run',{'code':str(run/'winsor2-readable.do'),'is_file':True,'cwd':str(run),'max_output_lines':100})
                    self.assertTrue(app.envelope_of(replay).get('success'),str(app.envelope_of(replay).get('error')))
                    pd.testing.assert_frame_equal(data,pd.read_stata(run/'reproduced.dta',convert_categoricals=False))
                    self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    replace=client.post('/api/winsor2',headers=headers,json={'variables':['x'],'lower':1,'upper':99,'mode':'replace'})
                    self.assertEqual(replace.status_code,200,replace.text)
                    self.assertEqual(replace.json()['report']['changed'][0]['rows'],2)
                    self.assertEqual(source.read_bytes(),original)
            finally:
                for p in reversed(patches):p.stop()
