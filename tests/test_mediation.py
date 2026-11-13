import json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import app
from mediation_engine import validate_mediation,compile_mediation,parse_mediation

SPEC={'method':'three_step','outcome':'y','exposure':'x','mediators':['m','m2'],'controls':['z'],'fixed_effects':[{'variables':['firm']},{'variables':['year']}],'se_type':'cluster','cluster':'firm'}
DATA={'variables':[{'name':v,'type':'float'} for v in ['y','x','m','m2','z','firm','year']]}
class Validation(unittest.TestCase):
    def test_plans_are_exact_and_validation_rejects_invalid(self):
        s=validate_mediation(SPEC,DATA);code,readable=compile_mediation(s,'a.txt')
        self.assertEqual(readable.count('reghdfe '),5);self.assertNotIn('predict',readable)
        s=validate_mediation({**SPEC,'method':'jiang'},DATA);self.assertEqual(compile_mediation(s,'a.txt')[1].count('reghdfe '),3)
        s=validate_mediation({**SPEC,'method':'fitted_two_stage'},DATA);code,readable=compile_mediation(s,'a.txt','md123456789abc')
        self.assertEqual(readable.count('reghdfe '),4);self.assertIn("predict `medfit1' if e(sample)",readable)
        self.assertIn("reghdfe y `medfit1' z, absorb(firm year) vce(cluster firm)",readable)
        for c in ({'mediators':['x']},{'mediators':['m','m']},{'method':'bad'},{'controls':['absent']}):
            with self.subTest(c=c),self.assertRaises(ValueError):validate_mediation({**SPEC,**c},DATA)

@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata and reghdfe')
class Real(unittest.TestCase):
    def test_all_methods_and_data_preservation(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*a,**kw):pass
            async def start(self,instructions,message):return SimpleNamespace(id='x',status='tool_calls',calls=[SimpleNamespace(name='prepare_mediation_task',arguments=json.dumps({**SPEC,'method':message,'intent':'run','continue_previous':False,'controls_specified':True}),call_id='c')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve();patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                rows=[]
                for f in range(1,31):
                    for yr in range(2016,2021):
                        x=(f*yr%37)/10;z=(f*yr%17)/10;noise=((f*yr)%11)*.03
                        m=.7*x+.3*z+noise+f*.02;m2=.4*x+.1*z+noise*.5
                        y=1.4*m+.4*x+.2*z+noise+(yr-2016)*.1
                        rows.append({'firm':f,'year':yr,'x':x,'z':z,'m':m,'m2':m2,'y':None if f==1 else y})
                source=tmp/'data.dta';pd.DataFrame(rows).to_stata(source,write_index=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as c:
                    headers={'Origin':'http://127.0.0.1:8765'};up=c.post('/api/raw-files',headers=headers,files=[('files',('data.dta',source.read_bytes(),'application/octet-stream'))]);fid=up.json()['added'][0]['id']
                    self.assertEqual(c.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200);before=c.get('/api/workspace').json()['dataset']
                    for method,count in [('three_step',5),('jiang',3),('fitted_two_stage',4)]:
                        response=c.post('/api/chat',headers=headers,json={'message':method});self.assertEqual(response.status_code,200,response.text);out=response.json()
                        self.assertIn('已完成',out['answer'],out);report=out['events'][0]['mediation_report'];self.assertEqual(len(report['models']),count)
                        self.assertEqual(report['models'][0]['n'],150 if method=='fitted_two_stage' else 145)
                        if method=='fitted_two_stage':self.assertEqual(report['models'][1]['n'],145);self.assertEqual(report['models'][1]['coefficients'][0]['variable'],'m_hat')
                        self.assertEqual(c.get('/api/workspace').json()['dataset'],before)
            finally:
                for p in reversed(patches):p.stop()
