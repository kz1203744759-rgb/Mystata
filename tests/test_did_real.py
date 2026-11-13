import json
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
from did_engine import validate_fixed_effects,compile_fixed_effects

class DidValidation(unittest.TestCase):
    def test_validation_uses_actual_names_and_requires_inference_choice(self):
        ds={'variables':[{'name':v,'type':'float'} for v in ['y','did','x','firm','year','industry','cluster']]}
        spec={'outcome':'y','explanatory_variables':['did','x'],'controls':[],'fixed_effects':[{'variables':['firm']},{'variables':['year']}],'se_type':'cluster','cluster':'cluster'}
        self.assertIn('reghdfe y did x, absorb(firm year) vce(cluster cluster)',compile_fixed_effects(validate_fixed_effects(spec,ds),'out.txt',True))
        for change in ({'outcome':'absent'},{'controls':['did']},{'explanatory_variables':[]},{'se_type':'unspecified'},{'cluster':''}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_fixed_effects({**spec,**change},ds)
        combined={**spec,'fixed_effects':[{'variables':['firm']},{'variables':['industry','year']}]}
        self.assertIn('absorb(firm industry#year)',compile_fixed_effects(validate_fixed_effects(combined,ds),'out.txt',True))
        for effects in [[{'variables':['industry;drop']}],[{'variables':['industry','missing']}],[{'variables':['year','year']}],[{'variables':['firm']},{'variables':['firm']}]]:
            with self.subTest(effects=effects),self.assertRaises(ValueError):validate_fixed_effects({**spec,'fixed_effects':effects},ds)

@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata and reghdfe')
class DidReal(unittest.TestCase):
    def test_registered_tool_runs_on_independent_synthetic_data(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*args,**kwargs):pass
            async def start(self,*args):
                spec={'outcome':'y','explanatory_variables':['x'],'controls':['did'],'fixed_effects':[{'variables':['firm']},{'variables':['industry','year']}],'se_type':'cluster','cluster':'firm'}
                return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='run_fixed_effects',arguments=json.dumps(spec),call_id='call')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve()
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                rows=[]
                for firm in range(1,21):
                    for year in range(2016,2021):
                        did=int(firm<=10 and year>=2019);x=(firm*year%17)/10
                        rows.append({'firm':firm,'year':year,'industry':firm%4,'did':did,'x':x,'y':firm*.3+(year-2016)*.4+did*2+x*.7+((firm*year)%7)*.03})
                source=tmp/'data.dta';pd.DataFrame(rows).to_stata(source,write_index=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    up=client.post('/api/raw-files',headers=headers,files=[('files',('data.dta',source.read_bytes(),'application/octet-stream'))])
                    fid=up.json()['added'][0]['id'];self.assertEqual(client.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    before=client.get('/api/workspace').json()['dataset']
                    response=client.post('/api/chat',headers=headers,json={'message':'用 y 对 did 和 x 回归，firm 与行业乘年份固定效应，firm 聚类'})
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json();self.assertIn('固定效应回归已完成',result['answer'])
                    report=result['events'][0]['fixed_effects_report'];self.assertEqual(report['n'],100);self.assertEqual(report['clusters'],20)
                    self.assertEqual(report['fixed_effects'],[['firm'],['industry','year']])
                    self.assertAlmostEqual(report['coefficients'][0]['coefficient'],.7,delta=.1)
                    self.assertAlmostEqual(report['coefficients'][1]['coefficient'],2,delta=.1)
                    self.assertEqual(client.get('/api/workspace').json()['dataset'],before)
                    self.assertTrue(any(a['name']=='fixed-effects-readable.do' for a in result['artifacts']))
            finally:
                for p in reversed(patches):p.stop()
