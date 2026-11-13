import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app
import profile_columns


class FieldListTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.root=Path(self.tmp.name).resolve()
        self.path=self.root/'raw.dta'
        pd.DataFrame({'id':np.array([1,2],dtype=np.int32),'year':np.array([2022,2023],dtype=np.float32),'name':['A','BB']}).to_stata(self.path,write_index=False,version=118,variable_labels={'id':'证券代码'})
        self.files={'a':{'filename':'ROE.dta','path':str(self.path),'format':'dta','observations':2,
            'variables':[{'name':'id'},{'name':'year'},{'name':'name'}]}}
        self.patches=[patch.object(app,'read_raw',return_value=self.files),
                      patch.object(app,'AsyncOpenAI',side_effect=AssertionError('must not call model')),
                      patch.object(app.worker,'call',side_effect=AssertionError('DTA header must not start Stata')),
                      patch.object(profile_columns,'duplicate_profile',side_effect=AssertionError('no duplicates'))]
        for p in self.patches:p.start()
        app.settings.update(api_key='',model='',provider='deepseek',base_url='https://api.deepseek.com')
        app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False,last_field_report=None)
        self.client=TestClient(app.app,base_url='http://127.0.0.1:8765')
        self.headers={'Origin':'http://127.0.0.1:8765'}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_header_returns_real_stata_type_format_and_label_without_reading_rows(self):
        before=self.path.read_bytes()
        with patch.object(pd,'read_stata',side_effect=AssertionError('should not read observations')):
            response=self.client.post('/api/profile-columns',headers=self.headers,json={'file_ids':['a']})
        self.assertEqual(response.status_code,200,response.text)
        data=response.json();report=json.loads(data['events'][0]['output']);item=report['files'][0]
        self.assertEqual(item['observations'],2)
        self.assertEqual([v['storage_type'] for v in item['columns']],['long','float','str2'])
        self.assertTrue(all(v['display_format'].startswith('%') for v in item['columns']))
        self.assertEqual(item['columns'][0]['label'],'证券代码')
        self.assertNotIn('duplicate_check',item)
        self.assertNotIn('format_profiles',item)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(data['loaded'])

    def test_plain_chat_uses_direct_path_without_model_or_key(self):
        response=self.client.post('/api/chat',headers=self.headers,json={'message':'检查全部字段和格式，不要检查重复','selected_file_ids':['a']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('存储类型',response.json()['answer'])
        self.assertEqual([e['tool'] for e in response.json()['events']],['profile_columns'])
        self.assertEqual(len(app.workspace['messages']),2)

    def test_compound_request_is_not_misclassified(self):
        for text in ['检查全部字段格式并检查重复','检查所有字段类型然后合并数据','检查所有字段格式及缺失值']:
            with self.subTest(text=text):self.assertFalse(app.field_only_request(text))
        self.assertTrue(app.field_only_request('请检查全部字段和格式，不要检查重复'))

    def test_corrupt_file_is_reported_not_silently_omitted(self):
        self.path.write_bytes(b'bad')
        response=self.client.post('/api/profile-columns',headers=self.headers,json={'file_ids':['a']})
        self.assertEqual(response.status_code,200,response.text)
        report=json.loads(response.json()['events'][0]['output'])
        self.assertIn('error',report['files'][0])
        self.assertIn('检查未完成',response.json()['answer'])


class ImportedFieldListTest(unittest.IsolatedAsyncioTestCase):
    async def test_csv_inspects_temp_frame_and_restores_existing_session(self):
        class Result:
            isError=False
            def __init__(self,data):self.structuredContent={'result':{'success':True,'data':data}}
        async def call(name,args):
            if name=='stata_run':return Result({'stdout':'FIELD_PROFILE_N=2\nFIELD_PROFILE_VAR|id|str6|%9s\n'})
            if name=='stata_inspect_data':return Result({'variables':[{'name':'id','type':'str6','format':'%9s','label':''}]})
            raise AssertionError(name)
        with patch.object(app,'STATA',__file__),patch.object(app.shutil,'which',return_value='uv'), \
             patch.object(app,'current_frame',new=AsyncMock(return_value='default')), \
             patch.object(app,'rollback_frame',new=AsyncMock(return_value=True)) as rollback, \
             patch.object(app.worker,'call',side_effect=call):
            result=await app.imported_field_header({'path':'D:/example.csv'})
        self.assertEqual(result['observations'],2)
        self.assertEqual(result['columns'][0]['display_format'],'%9s')
        rollback.assert_awaited_once()


if __name__=='__main__':unittest.main()
