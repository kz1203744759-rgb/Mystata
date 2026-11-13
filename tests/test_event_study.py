import json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import app
from event_study_engine import validate_event_study,compile_event_study,parse_event_study

SPEC={'outcome':'y','unit':'firm','year':'year','treated':'treated','cohort':'policy','min_period':-2,'max_period':1,'reference_period':-1,'controls':['x'],'fixed_effects':[{'variables':['firm']},{'variables':['year']}],'se_type':'cluster','cluster':'firm'}
DATA={'variables':[{'name':v,'type':'float'} for v in ['y','firm','year','treated','policy','x']]}
class EventValidation(unittest.TestCase):
    def test_code_and_guards(self):
        s=validate_event_study(SPEC,DATA);code=compile_event_study(s,'a.txt','ev123456789abc')
        self.assertIn('reghdfe y',code);self.assertIn('test `e2m\'',code);self.assertIn('absorb(firm year)',code)
        for c in ({'reference_period':-2},{'year':'year;drop'},{'treated':'absent'},{'se_type':'unspecified'}):
            with self.subTest(c=c),self.assertRaises(ValueError):validate_event_study({**SPEC,**c},DATA)
        report=parse_event_study('M|100|.3|1|1|19\nB|-2|.2|.1|.01|.39\nB|0|.3|.1|.11|.49\nB|1|.4|.1|.21|.59\n',s)
        self.assertTrue(report['points'][1]['reference']);self.assertEqual(report['pre_p'],.3)

@unittest.skipUnless(os.getenv('RUN_REAL_STATA_TESTS')=='1','requires Stata')
class EventReal(unittest.TestCase):
    def test_event_study_uses_temporary_frame_and_actual_stata(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*a,**kw):pass
            async def start(self,instructions,message):
                spec={**SPEC,'treated':'x','controls':[]} if message=='错误的处理组' else SPEC
                return SimpleNamespace(id='x',status='tool_calls',calls=[SimpleNamespace(name='run_event_study',arguments=json.dumps(spec),call_id='c')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve();patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'DATASETS',tmp/'datasets'),patch.object(app,'RAW',tmp/'datasets'/'raw'),patch.object(app,'RAW_MANIFEST',tmp/'datasets'/'raw'/'manifest.json'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                rows=[]
                for f in range(1,41):
                    for y in range(2017,2022):
                        t=int(f<=20);x=(f*y%17)/10
                        rows.append({'firm':f,'year':y,'treated':t,'policy':2019 if t else None,'x':x,'y':f*.2+(y-2017)*.3+t*(y>=2019)*1.5+.7*x+((f*y)%13)*.02})
                source=tmp/'data.dta';pd.DataFrame(rows).to_stata(source,write_index=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as c:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    up=c.post('/api/raw-files',headers=headers,files=[('files',('data.dta',source.read_bytes(),'application/octet-stream'))]);fid=up.json()['added'][0]['id']
                    self.assertEqual(c.post(f'/api/raw-files/{fid}/activate',headers=headers).status_code,200)
                    before=c.get('/api/workspace').json()['dataset']
                    response=c.post('/api/chat',headers=headers,json={'message':'运行传统事件研究'})
                    self.assertEqual(response.status_code,200,response.text);out=response.json();self.assertIn('已完成',out['answer'],out)
                    report=out['events'][0]['event_study_report'];self.assertEqual(len(report['points']),4);self.assertEqual(report['n'],200)
                    self.assertEqual(c.get('/api/workspace').json()['dataset'],before)
                    failed=c.post('/api/chat',headers=headers,json={'message':'错误的处理组'}).json()
                    self.assertTrue(failed['events'][0]['error']);self.assertTrue(failed['loaded']);self.assertEqual(c.get('/api/workspace').json()['dataset'],before)
            finally:
                for p in reversed(patches):p.stop()
