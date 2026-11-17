"""Opt-in integration with Stata; uses only temporary synthetic data."""
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
import app
from test_agent_rounds import FakeClient, FakeSession


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata')
class DtaChangeRealTest(unittest.TestCase):
    def test_two_files_delete_keep_and_independent_undo(self):
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project) as temp:
            root=Path(temp).resolve();shutil.copyfile(project/'mcp_launcher.py',root/'mcp_launcher.py')
            patches=[patch.object(app,'ROOT',root),patch.object(app,'RUNS',root/'runs'),
                     patch.object(app,'DATASETS',root/'datasets'),patch.object(app,'RAW',root/'datasets'/'raw'),
                     patch.object(app,'RAW_MANIFEST',root/'datasets'/'raw'/'manifest.json'),patch.object(app,'CONTEXT_DB',root/'state.sqlite'),
                     patch.object(app,'AsyncOpenAI',FakeClient),patch.object(app,'ModelSession',FakeSession)]
            for p in patches:p.start()
            old_settings=app.settings.copy()
            try:
                app.settings.update(api_key='test',model='test',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False,research_variables={},dataset_revision=None)
                sources=[]
                for name,frame in [('X.dta',pd.DataFrame({'stkcd':[1,2],'year':[2020,2021],'ln数字化转型':[1.,2.],'other':[3,4]})),
                                   ('Y.dta',pd.DataFrame({'id':[1,2],'证券简称':['a','b'],'省份':['c','d'],'城市':['e','f'],'区县':['g','h'],'行业代码':[1,2],'行业名称':['i','j']}))]:
                    buf=io.BytesIO();frame.to_stata(buf,write_index=False,version=118);sources.append((name,buf.getvalue()))
                headers={'Origin':'http://127.0.0.1:8765'}
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    result=client.post('/api/raw-files',headers=headers,files=[('files',(n,b,'application/octet-stream')) for n,b in sources])
                    self.assertEqual(result.status_code,200,result.text)
                    ids={f['filename']:f['id'] for f in result.json()['added']}
                    ops=[{'target':'raw','file_id':ids['Y.dta'],'action':'drop','variables':['证券简称','省份','城市','区县','行业代码','行业名称']},
                         {'target':'raw','file_id':ids['X.dta'],'action':'keep','variables':['stkcd','year','ln数字化转型']}]
                    call=SimpleNamespace(name='edit_dta_columns_batch',arguments=json.dumps({'operations':ops}),call_id='batch')
                    FakeSession.responses=[SimpleNamespace(id='r',status='tool_calls',text='',calls=[call])]
                    result=client.post('/api/chat',headers=headers,json={'message':'删除Y的证券简称、省份、城市、区县、行业代码、行业名称，仅保留X的stkcd、year、ln数字化转型','selected_file_ids':list(ids.values())})
                    self.assertEqual(result.status_code,200,result.text)
                    self.assertEqual(len(result.json()['events']),2,result.text)
                    x=root/'datasets'/'raw'/(ids['X.dta']+'.dta');y=root/'datasets'/'raw'/(ids['Y.dta']+'.dta')
                    self.assertEqual(list(pd.read_stata(x).columns),['stkcd','year','ln数字化转型'])
                    self.assertEqual(list(pd.read_stata(y).columns),['id'])
                    for name,original in sources:
                        undo=client.post('/api/dta/undo',headers=headers,json={'target':'raw','file_id':ids[name]})
                        self.assertEqual(undo.status_code,200,undo.text)
                        self.assertEqual((root/'datasets'/'raw'/(ids[name]+'.dta')).read_bytes(),original)
            finally:
                app.settings.clear();app.settings.update(old_settings)
                for p in reversed(patches):p.stop()

    def test_drop_and_undo_update_file_and_active_dataset(self):
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project) as temp:
            root=Path(temp).resolve();shutil.copyfile(project/'mcp_launcher.py',root/'mcp_launcher.py')
            patches=[patch.object(app,'ROOT',root),patch.object(app,'RUNS',root/'runs'),
                     patch.object(app,'DATASETS',root/'datasets'),patch.object(app,'RAW',root/'datasets'/'raw'),
                     patch.object(app,'RAW_MANIFEST',root/'datasets'/'raw'/'manifest.json'),patch.object(app,'CONTEXT_DB',root/'state.sqlite')]
            for p in patches:p.start()
            try:
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False,research_variables={},dataset_revision=None)
                data=io.BytesIO();pd.DataFrame({'id':[1,2],'keep_me':[10.,20.],'remove_me':[30.,40.]}).to_stata(data,write_index=False,version=118,variable_labels={'keep_me':'keep label','remove_me':'remove label'})
                original=data.getvalue();headers={'Origin':'http://127.0.0.1:8765'}
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    upload=client.post('/api/raw-files',headers=headers,files=[('files',('sample.dta',original,'application/octet-stream'))])
                    self.assertEqual(upload.status_code,200,upload.text)
                    fid=upload.json()['added'][0]['id'];raw=root/'datasets'/'raw'/(fid+'.dta')
                    activate=client.post(f'/api/raw-files/{fid}/activate',headers=headers)
                    self.assertEqual(activate.status_code,200,activate.text)
                    revision=activate.json()['dataset_revision']
                    selected=client.post('/api/research-variables',headers=headers,json={'target':'active','role':'x','variables':['remove_me'],'dataset_revision':revision})
                    self.assertEqual(selected.status_code,200,selected.text)
                    drop=client.post('/api/dta/drop-columns',headers=headers,json={'target':'raw','file_id':fid,'variables':['remove_me']})
                    self.assertEqual(drop.status_code,200,drop.text)
                    self.assertNotIn('remove_me',[v['name'] for v in drop.json()['dataset']['variables']])
                    self.assertEqual(drop.json()['research_variables']['x'],[])
                    self.assertNotEqual(drop.json()['dataset_revision'],revision)
                    self.assertNotEqual(raw.read_bytes(),original)
                    do=client.get(drop.json()['event']['readable_url'])
                    self.assertEqual(do.status_code,200,do.text)
                    self.assertIn('drop remove_me',do.text)
                    changed=raw.read_bytes();raw.write_bytes(changed+b'external')
                    conflict=client.post('/api/dta/undo',headers=headers,json={'target':'active','file_id':''})
                    self.assertEqual(conflict.status_code,400,conflict.text)
                    self.assertEqual(raw.read_bytes(),changed+b'external')
                    raw.write_bytes(changed)
                    undo=client.post('/api/dta/undo',headers=headers,json={'target':'active','file_id':''})
                    self.assertEqual(undo.status_code,200,undo.text)
                    self.assertIn('remove_me',[v['name'] for v in undo.json()['dataset']['variables']])
                    self.assertEqual(raw.read_bytes(),original)
                    self.assertIn('remove_me',[v['name'] for v in undo.json()['raw_files'][0]['variables']])
            finally:
                for p in reversed(patches):p.stop()
