import json
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
import profile_columns as profile


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT)
        self.root=Path(self.temp.name)
        path=self.root/'table.csv'
        path.write_text('id,year,province,value\n000001,2020, 北京 ,5\n000001,2020,北京,\n000001,2020,北京,7\n000002,2021,浙江,8\n000002,2021,浙江,9\n000003,2022,浙江,10\n',encoding='utf-8')
        self.files={'a':{'filename':'table.csv','path':str(path),'format':'csv','observations':6,
                    'variables':[{'name':n,'type':'object','label':'','missing':123} for n in ['id','year','province','value']]}}
        self.roles=[{'file_id':'a','column':'id','role':'stock_code'}, {'file_id':'a','column':'year','role':'year'}, {'file_id':'a','column':'province','role':'province'}]
        self.checks=[{'file_id':'a','columns':['id','year']}]

    def tearDown(self):self.temp.cleanup()

    def run_profile(self,message,checks=None,roles=None,offset=0,page_size=30):
        return profile.profile_files(self.files,['a'],self.roles if roles is None else roles,checks or [],offset,page_size,message)

    def test_default_no_duplicate_computation_or_missing_statistics(self):
        with patch.object(profile,'duplicate_profile',side_effect=AssertionError('duplicate check must not run')):
            result=self.run_profile('检查字段和格式')
        file=result['files'][0]
        self.assertEqual([c['name'] for c in file['columns']],['id','year','province','value'])
        self.assertNotIn('duplicate_check',file)
        self.assertNotIn('missing',json.dumps(result,ensure_ascii=False))
        self.assertEqual(file['format_profiles'][0]['leading_zero_strings'],6)
        self.assertEqual(file['format_profiles'][2]['space_variants'],1)

    def test_model_cannot_silently_request_duplicates(self):
        for message in ['检查字段','检查 id 和 year 的格式','不要检查 id 和 year 的重复','请检查重复','检查 id 和 year，ROE 是唯一的解释变量','检查 id 和 year 格式，不要重复提醒']:
            with self.subTest(message=message),patch.object(profile,'duplicate_profile',side_effect=AssertionError('must not run')):
                result=self.run_profile(message,self.checks)
                self.assertIn('未执行重复检查',result['duplicate_request_status'])
                self.assertNotIn('duplicate_check',result['files'][0])

    def test_explicit_composite_duplicate_counts_without_deletion(self):
        before=Path(self.files['a']['path']).read_bytes()
        result=self.run_profile('检查 id 和 year 组合是否有重复',self.checks)
        check=result['files'][0]['duplicate_check']
        self.assertEqual((check['duplicate_groups'],check['rows_in_duplicate_groups'],check['surplus_rows']),(2,5,3))
        self.assertEqual(Path(self.files['a']['path']).read_bytes(),before)
        self.assertNotIn('missing',json.dumps(result,ensure_ascii=False))

    def test_negated_missing_does_not_cancel_explicit_duplicate_request(self):
        result=self.run_profile('不检查缺失，只检查 id 和 year 是否重复',self.checks)
        self.assertEqual(result['files'][0]['duplicate_check']['duplicate_groups'],2)

    def test_explicit_key_uniqueness_is_a_duplicate_request(self):
        result=self.run_profile('检查 id 和 year 组合是否唯一',self.checks)
        self.assertEqual(result['files'][0]['duplicate_check']['duplicate_groups'],2)

    def test_semantic_field_names_can_authorize_mapped_code_and_year(self):
        result=self.run_profile('检查股票代码和年份组合是否重复',self.checks)
        self.assertEqual(result['files'][0]['duplicate_check']['duplicate_groups'],2)

    def test_directory_pagination_and_ambiguous_id(self):
        result=self.run_profile('查看字段',roles=[],offset=0,page_size=2)
        file=result['files'][0]
        self.assertEqual(file['next_offset'],2)
        self.assertIsNone(file['columns'][0]['candidate_role'])
        self.assertEqual(file['columns'][1]['candidate_role'],'year')

    def test_numeric_region_is_not_assumed_to_be_a_name(self):
        result=profile.format_profile(pd.Series([110000,310000]),'province')
        self.assertEqual(result['non_string_values'],2)
        self.assertIn('可能是地区编码',result['note'])

    def test_stata_and_excel_formats_and_stata_missing_keys(self):
        frame=pd.DataFrame({'id':[1.0,float('nan'),float('nan')],'year':[2020,2020,2020]})
        for suffix in ['dta','xlsx']:
            with self.subTest(suffix=suffix):
                path=self.root/f'input.{suffix}'
                if suffix=='dta':frame.to_stata(path,write_index=False)
                else:frame.to_excel(path,index=False)
                metadata={'b':{'filename':path.name,'path':str(path),'format':suffix,'observations':3,
                               'variables':[{'name':'id','type':'number','label':''},{'name':'year','type':'number','label':''}]}}
                result=profile.profile_files(metadata,['b'],[],[{'file_id':'b','columns':['id','year']}],0,30,'检查 id 和 year 是否重复')
                self.assertEqual(result['files'][0]['duplicate_check']['rows_in_duplicate_groups'],2)


class FakeClient:
    def __init__(self,**_):pass
    async def close(self):pass


class FakeSession:
    output=None
    instruction=''
    arguments={}
    def __init__(self,*args,**kwargs):pass
    async def start(self,instruction,message):
        FakeSession.instruction=instruction
        return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='profile_columns',arguments=json.dumps(FakeSession.arguments),call_id='c1')])
    async def resume(self,response,outputs):
        FakeSession.output=json.loads(outputs[0]['output'])
        return SimpleNamespace(id='two',status='completed',text='字段检查完成。',calls=[])
    def completed_history(self):return []


class ProfileAgentIntegrationTest(unittest.TestCase):
    def test_agent_can_call_tool_and_get_real_report_without_stata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp);stata=root/'not-installed.exe'
            raw={'a':{'filename':'real.csv','path':str(root/'real.csv'),'format':'csv','observations':2,
                      'variables':[{'name':'id','type':'object','label':'代码'},{'name':'year','type':'int','label':'年份'}]}}
            patches=[patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value=raw),
                     patch.object(app,'AsyncOpenAI',FakeClient),patch.object(app,'ModelSession',FakeSession),patch.object(app.shutil,'which',return_value=None),
                     patch.object(app.worker,'call',side_effect=AssertionError('profile should not call Stata'))]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake-key',model='fake-model',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                FakeSession.arguments={'file_ids':['a'],'column_roles':[],'duplicate_checks':[],'offset':0,'page_size':30}
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'检查字段','selected_file_ids':['a']})
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(FakeSession.output['success'])
                self.assertEqual(FakeSession.output['data']['files'][0]['column_count'],2)
                self.assertIn('"file_id": "a"',FakeSession.instruction)
                self.assertIn('当前 Stata 或 uv 不可用',FakeSession.instruction)
                self.assertEqual(response.json()['events'][0]['tool'],'profile_columns')
                self.assertFalse(response.json()['loaded'])
            finally:
                for p in reversed(patches):p.stop()

    def test_duplicate_samples_are_local_only_and_agent_receives_counts(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp);stata=root/'stata.exe';stata.touch()
            data=root/'real.csv';data.write_text('id,year\n000001,2020\n000001,2020\n',encoding='utf-8')
            raw={'a':{'filename':'real.csv','path':str(data),'format':'csv','observations':2,
                      'variables':[{'name':'id','type':'object','label':''},{'name':'year','type':'object','label':''}]}}
            patches=[patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value=raw),
                     patch.object(app,'AsyncOpenAI',FakeClient),patch.object(app,'ModelSession',FakeSession),patch.object(app.shutil,'which',return_value='uv')]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake-key',model='fake-model',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                FakeSession.arguments={'file_ids':['a'],'column_roles':[],'duplicate_checks':[{'file_id':'a','columns':['id','year']}],'offset':0,'page_size':30}
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'请检查 id 和 year 的重复','selected_file_ids':['a']})
                self.assertEqual(response.status_code,200,response.text)
                local=json.loads(response.json()['events'][0]['output'])
                self.assertEqual(local['files'][0]['duplicate_check']['examples'][0]['id'],'000001')
                model=FakeSession.output['data']['files'][0]['duplicate_check']
                self.assertEqual(model['rows_in_duplicate_groups'],2)
                self.assertNotIn('examples',model)
                self.assertNotIn('000001',json.dumps(FakeSession.output))
            finally:
                for p in reversed(patches):p.stop()


if __name__=='__main__':unittest.main()
