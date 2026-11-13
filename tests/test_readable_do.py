import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from readable_do import readable_etl,readable_step
from etl_engine import compile_plan
import app


class ReadableDoTest(unittest.TestCase):
    def setUp(self):
        self.files={'a':{'filename':'ROE.dta','path':'D:/data/random_a.dta','variables':[{'name':n} for n in ('code','year','name','ROE')]},
                    'b':{'filename':'SOE.dta','path':'D:/data/random_b.dta','variables':[{'name':n} for n in ('stock_code','year','SOE')]}}
        self.plan={'file_ids':['a','b'],'mode':'merge','cardinality':'1:1','keys':['id','year'],'mappings':[
            {'target':'id','sources':{'a':0,'b':0},'convert':'none','normalize':'stock','keep':True},
            {'target':'year','sources':{'a':1,'b':1},'convert':'none','normalize':'year','keep':True},
            {'target':'ROE','sources':{'a':3},'convert':'none','normalize':'none','keep':True},
            {'target':'SOE','sources':{'b':2},'convert':'none','normalize':'none','keep':True}]}

    def test_dta_uses_original_field_names_and_named_files(self):
        code=readable_etl(self.plan,self.files,Path('run'),'abcdef123456789')
        self.assertIn('* 文件 1：ROE.dta',code)
        self.assertIn('keep code year ROE',code)
        self.assertIn('rename code id',code)
        self.assertIn('rename stock_code id',code)
        self.assertNotIn('local etl_var',code)
        self.assertIn('recast long id',code)
        self.assertIn('recast float year',code)
        self.assertIn('merge 1:1 id year',code)
        self.assertIn('reproduced.dta',code)
        self.assertNotIn('active.dta',code)

    def test_collision_uses_safe_fallback(self):
        self.files['a']['variables'][0]['name']='year'
        self.files['a']['variables'][1]['name']='code'
        code=readable_etl(self.plan,self.files,Path('run'),'abcdef123456789')
        self.assertIn('按列定位',code)
        self.assertIn('第 1 列 year → id',code)
        self.assertIn('local etl_var',code)

    def test_regression_and_graph_steps_preserve_code_and_needed_aliases(self):
        raw=[{'file':'ROE.dta','path':'D:/data/random_a.dta','stata_macro':'ea_raw_1'},
             {'file':'other.dta','path':'D:/data/random_b.dta','stata_macro':'ea_raw_2'}]
        code='use "D:/data/random_a.dta", clear\nregress y x\ntwoway scatter y x'
        readable=readable_step(code,raw,True)
        self.assertIn('* 原始文件：ROE.dta',readable)
        self.assertNotIn('other.dta',readable)
        self.assertIn('use "D:/data/random_a.dta", clear',readable)
        self.assertIn('regress y x\ntwoway scatter y x',readable)
        self.assertIn('本次执行状态：成功',readable)
        self.assertIn('本次执行状态：失败',readable_step('bad command',raw,False))

    def test_earlier_etl_run_gets_readable_view_and_download(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            runs=Path(temp)/'runs';directory=runs/'previous';directory.mkdir(parents=True)
            (directory/'etl-plan.json').write_text(json.dumps(self.plan),encoding='utf-8')
            code,_=compile_plan(self.plan,self.files,directory,directory/'active.dta','abcdef123456789')
            app.workspace.update(dataset=None,path=None,loaded=False,messages=[],events=[{'tool':'etl','code':code,'error':False}],artifacts=[])
            with patch.object(app,'RUNS',runs),patch.object(app,'read_raw',return_value=self.files):
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                event=client.get('/api/workspace').json()['events'][0]
                self.assertIn('rename code id',event['readable_code'])
                response=client.get(event['readable_url'])
                self.assertEqual(response.status_code,200)
                self.assertIn('rename code id',response.content.decode('utf-8'))
