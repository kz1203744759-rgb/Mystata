"""Optional Stata comparison of executed and exported scripts on synthetic data."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires local Stata')
class ReadableRealTest(unittest.TestCase):
    def test_dta_direct_and_collision_fallback_match_actual_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            with patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'):
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    for collision in (False,True):
                        left=tmp/('left'+str(collision)+'.dta');right=tmp/('right'+str(collision)+'.dta')
                        if collision:
                            pd.DataFrame({'year':[1,2,3],'code':[2020,2021,2021],'sales':[12.,None,5.]}).to_stata(left,write_index=False)
                            akeys=(0,1)
                        else:
                            pd.DataFrame({'code':[1,2,3],'year':[2020,2021,2021],'sales':[12.,None,5.]}).to_stata(left,write_index=False)
                            akeys=(0,1)
                        pd.DataFrame({'stock':[1,2,4],'year':[2020,2021,2021],'cost':[4.,9.,7.]}).to_stata(right,write_index=False)
                        files=[('files',(left.name,left.read_bytes(),'application/octet-stream')),('files',(right.name,right.read_bytes(),'application/octet-stream'))]
                        uploaded=client.post('/api/raw-files',headers=headers,files=files)
                        self.assertEqual(uploaded.status_code,200,uploaded.text)
                        a,b=[f['id'] for f in uploaded.json()['added']]
                        plan={'file_ids':[a,b],'mode':'merge','cardinality':'1:1','keys':['id','year'],'mappings':[
                            {'target':'id','sources':{a:akeys[0],b:0},'normalize':'stock'},
                            {'target':'year','sources':{a:akeys[1],b:1},'normalize':'year'},
                            {'target':'sales','sources':{a:2}}, {'target':'cost','sources':{b:2}}]}
                        merged=client.post('/api/etl/run',headers=headers,json=plan)
                        self.assertEqual(merged.status_code,200,merged.text)
                        result=merged.json();event=result['event']
                        self.assertIn('readable_code',event)
                        self.assertEqual('local etl_var' in event['readable_code'],collision)
                        artifact=next(x for x in result['artifacts'] if x['name']=='etl-readable.do')
                        run_id=artifact['url'].split('/')[3];run=tmp/'runs'/run_id
                        actual=pd.read_stata(run/'active.dta',convert_categoricals=False)
                        executed=client.portal.call(app.worker.call,'stata_run',{'code':str(run/'etl-readable.do'),'is_file':True,'cwd':str(run),'max_output_lines':100})
                        env=app.envelope_of(executed)
                        self.assertTrue(env.get('success'),str(env.get('error')))
                        reproduced=pd.read_stata(run/'reproduced.dta',convert_categoricals=False)
                        pd.testing.assert_frame_equal(actual,reproduced)
