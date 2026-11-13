"""Optional integration on an isolated synthetic Stata dataset."""
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

@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata')
class StatisticsRealTest(unittest.TestCase):
    def test_real_statistics_keep_active_data_and_use_pairwise_samples(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json')]
            for p in patches:p.start()
            try:
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    source=tmp/'source.dta'
                    pd.DataFrame({'x':[1,2,3,4,5],'y':[2,4,6,8,10],'z':[1,None,3,None,5],'constant':[7,7,7,7,7],'v':[2,4,6,10,8]}).to_stata(source,write_index=False)
                    upload=client.post('/api/raw-files',headers=headers,files=[('files',('source.dta',source.read_bytes(),'application/octet-stream'))])
                    fid=upload.json()['added'][0]['id']
                    self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    before=client.get('/api/workspace').json()['dataset']
                    response=client.post('/api/statistics',headers=headers,json={'variables':['x','y','z','constant','v'],'kinds':['descriptive','correlation']})
                    self.assertEqual(response.status_code,200,response.text)
                    report=response.json()['report']
                    self.assertEqual(report['descriptive'][0]['n'],5)
                    self.assertEqual(report['descriptive'][0]['mean'],3)
                    self.assertEqual(report['descriptive'][0]['median'],3)
                    self.assertAlmostEqual(report['descriptive'][0]['sd'],1.58113883008419)
                    self.assertAlmostEqual(report['correlation'][0][1]['r'],1)
                    self.assertLess(report['correlation'][0][1]['p'],1e-15)
                    self.assertEqual(report['correlation'][0][2]['n'],3)
                    self.assertIsNone(report['correlation'][0][3]['r'])
                    self.assertAlmostEqual(report['correlation'][0][4]['r'],.9)
                    self.assertAlmostEqual(report['correlation'][0][4]['p'],.0373860734685,places=8)
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],before)
                    self.assertTrue(any(a['name']=='statistics.do' for a in response.json()['artifacts']))
            finally:
                for p in reversed(patches):p.stop()
