"""Optional synthetic integration test; does not access user datasets."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires local Stata')
class RealMergePreview(unittest.TestCase):
    def test_id_only_matched_complete_case(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            with patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'):
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    inputs=[('files',('left.csv',b'code,year,name,sales\n000001,2020,A,12\n000002,2020,B,\n000003,2020,C,25\n','text/csv')),
                            ('files',('right.csv',b'code,year,cost\n1,2020,4\n2,2020,9\n4,2020,6\n','text/csv'))]
                    upload=client.post('/api/raw-files',headers=headers,files=inputs)
                    self.assertEqual(upload.status_code,200,upload.text)
                    a,b=[item['id'] for item in upload.json()['added']]
                    mappings=[{'target':'id','sources':{a:0,b:0},'normalize':'stock'},
                              {'target':'year','sources':{a:1,b:1},'normalize':'year'},
                              {'target':'name','sources':{a:2},'keep':False},
                              {'target':'sales','sources':{a:3}},{'target':'cost','sources':{b:2}}]
                    plan={'file_ids':[a,b],'mode':'merge','cardinality':'1:1','keys':['id'],'mappings':mappings}
                    before=client.get('/api/workspace').json()['dataset']
                    preview=client.post('/api/etl/preview',headers=headers,json=plan)
                    self.assertEqual(preview.status_code,200,preview.text)
                    result=preview.json()
                    self.assertTrue(result['ok'],result.get('error'))
                    for key,value in {'MERGE_1_MASTER_ONLY':1,'MERGE_1_USING_ONLY':1,'MERGE_1_MATCHED':2,'FINAL_BEFORE_MISSING':2,'ANALYSIS_MISSING_ROWS':1,'FINAL_ROWS':1}.items():
                        self.assertEqual(result['metrics'].get(key),value,(key,result['metrics']))
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],before)
                    merged=client.post('/api/etl/run',headers=headers,json=plan)
                    self.assertEqual(merged.status_code,200,merged.text)
                    dataset=merged.json()['dataset']
                    self.assertEqual(dataset['observations'],1)
                    self.assertNotIn('name',[v['name'] for v in dataset['variables']])
                    result=client.portal.call(app.worker.call,'stata_run',{'code':'local id_type : type id\nlocal year_type : type year\ndisplay "CHECK_ID_TYPE=`id_type\'"\ndisplay "CHECK_YEAR_TYPE=`year_type\'"','max_output_lines':100})
                    output=app.envelope_of(result)['data']['stdout']
                    self.assertIn('CHECK_ID_TYPE=long',output)
                    self.assertIn('CHECK_YEAR_TYPE=float',output)
