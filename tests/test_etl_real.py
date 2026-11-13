"""Optional integration test: requires a working local Stata and uv."""
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


@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','set RUN_REAL_STATA_TESTS=1 to run Stata')
class RealEtlTest(unittest.TestCase):
    def test_multifile_merge_append_and_rollback(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tmp=Path(tmp).resolve()
            with patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'):
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    files=[('files',('left.csv','stkcd,year,sales\n000001,2020,12\n000002,2021,24\n'.encode('utf-8'),'text/csv')),
                           ('files',('right.csv','证券代码,年份,cost\n000001,2020,4\n000002,2021,9\n'.encode('utf-8'),'text/csv'))]
                    upload=client.post('/api/raw-files',headers=headers,files=files)
                    self.assertEqual(upload.status_code,200,upload.text)
                    raw=upload.json()['added']; self.assertEqual(len(raw),2)
                    a,b=[x['id'] for x in raw]
                    self.assertEqual(raw[0]['preview'][0][0],'000001')
                    first=client.post(f'/api/raw-files/{a}/activate',headers=headers)
                    self.assertEqual(first.status_code,200,first.text)
                    mapping=[{'target':'stock_code','sources':{a:0,b:0},'convert':'none','keep':True},
                             {'target':'year','sources':{a:1,b:1},'convert':'numeric','keep':True},
                             {'target':'sales','sources':{a:2},'convert':'numeric','keep':True},
                             {'target':'cost','sources':{b:2},'convert':'numeric','keep':True}]
                    plan={'file_ids':[a,b],'mode':'merge','cardinality':'1:1','keys':['stock_code','year'],'mappings':mapping}
                    merged=client.post('/api/etl/run',headers=headers,json=plan)
                    self.assertEqual(merged.status_code,200,merged.text)
                    self.assertEqual(merged.json()['dataset']['observations'],2)
                    columns=[v['name'] for v in merged.json()['dataset']['variables']]
                    self.assertEqual(merged.json()['dataset']['preview'][0][columns.index('stock_code')],'000001')
                    client.portal.call(app.worker.call,'stata_run',{'code':'generate doubled = sales * 2','max_output_lines':100})
                    client.portal.call(app.sync_active_dataset)
                    original=client.get('/api/workspace').json()['dataset']
                    self.assertIn('doubled',[v['name'] for v in original['variables']])
                    self.assertEqual(original['preview'][0][-1],24)
                    # Different nonmissing values for the same mapped non-key variable must fail.
                    conflict={'file_ids':[a,b],'mode':'merge','cardinality':'1:1','keys':['stock_code','year'],
                        'mappings':mapping[:2]+[{'target':'amount','sources':{a:2,b:2},'convert':'numeric','keep':True}]}
                    conflict_preview=client.post('/api/etl/preview',headers=headers,json=conflict)
                    self.assertEqual(conflict_preview.status_code,200,conflict_preview.text)
                    self.assertFalse(conflict_preview.json()['ok'])
                    self.assertEqual(conflict_preview.json()['metrics'].get('FIELD_1_amount'),2,conflict_preview.text)
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],original)
                    resolved=client.post('/api/etl/preview',headers=headers,json={**conflict,'conflict_policy':'using'})
                    self.assertTrue(resolved.json()['ok'],resolved.text)
                    self.assertEqual(resolved.json()['metrics'].get('FIELD_1_amount'),2,resolved.text)
                    failed=client.post('/api/etl/run',headers=headers,json=conflict)
                    self.assertEqual(failed.status_code,400,failed.text)
                    self.assertTrue(failed.json()['restored'],failed.text)
                    self.assertTrue(failed.json()['event']['error'])
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],original)
                    state=client.portal.call(app.worker.call,'stata_run',{'code':'display "ETL_CHECK_N=" _N','max_output_lines':100})
                    self.assertIn('ETL_CHECK_N=2',app.envelope_of(state)['data']['stdout'])
                    append=client.post('/api/etl/run',headers=headers,json={**plan,'mode':'append','keys':[]})
                    self.assertEqual(append.status_code,200,append.text)
                    self.assertEqual(append.json()['dataset']['observations'],4)
                    invalid=client.post('/api/raw-files',headers=headers,files=[('files',('invalid.csv',b'stkcd,year\n000001,not-a-year\n','text/csv'))])
                    c=invalid.json()['added'][0]['id']
                    bad_plan={'file_ids':[a,c],'mode':'append','cardinality':'1:1','keys':[],
                        'mappings':[{'target':'stock_code','sources':{a:0,c:0},'convert':'none','keep':True},
                                    {'target':'year','sources':{a:1,c:1},'convert':'numeric','keep':True}]}
                    bad=client.post('/api/etl/run',headers=headers,json=bad_plan)
                    self.assertEqual(bad.status_code,400,bad.text)
                    self.assertTrue(bad.json()['restored'],bad.text)
                    self.assertEqual(client.get('/api/workspace').json()['dataset']['observations'],4)

                    inputs=[('files',('n1.csv','code,year,province,sales\n000002,2023, 北京 ,5\n,2023,浙江,7\n000003,2022,浙江,\n'.encode('utf-8'),'text/csv')),
                            ('files',('n2.csv','code,year,province,cost\n2,2023,北京,4\n3,2022,浙江,8\n'.encode('utf-8'),'text/csv'))]
                    added=client.post('/api/raw-files',headers=headers,files=inputs).json()['added']
                    x,y=[item['id'] for item in added]
                    normalized={'file_ids':[x,y],'mode':'merge','cardinality':'1:1','keys':['code','year'],'drop_missing_keys':True,'drop_missing':['sales'],
                        'mappings':[{'target':'code','sources':{x:0,y:0},'normalize':'stock','keep':True},
                                    {'target':'year','sources':{x:1,y:1},'normalize':'year','keep':True},
                                    {'target':'province','sources':{x:2,y:2},'normalize':'region','keep':True},
                                    {'target':'sales','sources':{x:3},'convert':'numeric','keep':True},
                                    {'target':'cost','sources':{y:3},'convert':'numeric','keep':True}]}
                    before=client.get('/api/workspace').json()['dataset']
                    preview=client.post('/api/etl/preview',headers=headers,json=normalized)
                    self.assertEqual(preview.status_code,200,preview.text)
                    self.assertTrue(preview.json()['ok'],preview.text)
                    self.assertEqual(preview.json()['metrics'].get('SOURCE_1_MISSING_KEYS'),1,repr(preview.json()['metrics'])+' output-start:'+repr(preview.json()['output'][:500]))
                    self.assertEqual(preview.json()['metrics']['ANALYSIS_MISSING_ROWS'],1)
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],before)
                    merged=client.post('/api/etl/run',headers=headers,json=normalized)
                    self.assertEqual(merged.status_code,200,merged.text)
                    self.assertEqual(merged.json()['dataset']['observations'],1)
                    self.assertEqual(merged.json()['dataset']['variables'][0]['display_format'],'stock_6')
                    dates=client.post('/api/raw-files',headers=headers,files=[('files',('d1.csv',b'code,date\n000002,2023-12-31\n','text/csv')),('files',('d2.csv',b'code,date\n2,20231231\n','text/csv'))]).json()['added']
                    d1,d2=[f['id'] for f in dates]
                    dateplan={'file_ids':[d1,d2],'mode':'merge','keys':['code','year'],
                        'mappings':[{'target':'code','sources':{d1:0,d2:0},'normalize':'stock'}, {'target':'year','sources':{d1:1,d2:1},'normalize':'date_ymd'}]}
                    date_preview=client.post('/api/etl/preview',headers=headers,json=dateplan)
                    self.assertTrue(date_preview.json()['ok'],date_preview.text)
                    self.assertEqual(date_preview.json()['metrics']['MERGE_1_MATCHED'],1)

if __name__=='__main__': unittest.main()
