import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import app
from mediation_workflow import prepare_mediation,redirect_mediation_code

DATA={'filename':'data.dta','observations':10,'variables':[{'name':v,'type':'float'} for v in ['y','x','m','firm','year']]}
PLAN={'intent':'run','continue_previous':False,'method':'fitted_two_stage','outcome':'y','exposure':'x','mediators':['m'],'controls':[],'controls_specified':True,'fixed_effects':[{'variables':['firm']},{'variables':['year']}],'se_type':'cluster','cluster':''}

class Workflow(unittest.TestCase):
    def test_redirect_only_supported_generated_mediation_code(self):
        code='reghdfe m x, absorb(firm year) vce(cluster firm)\npredict m_hat if e(sample)\nreghdfe y m_hat, absorb(firm year) vce(cluster firm)'
        self.assertTrue(redirect_mediation_code('确认','请进行中介检验',code))
        self.assertFalse(redirect_mediation_code('请执行我提供的代码','中介检验',code))
        self.assertFalse(redirect_mediation_code('确认','一般回归',code))
        self.assertFalse(redirect_mediation_code('中介检验','',code.replace('cluster firm','cluster firm city')))
        self.assertFalse(redirect_mediation_code('中介检验','',code.replace('reghdfe m x,','reghdfe m x if year>2000,')))
    def test_merge_only_on_continuation_and_distinguish_no_controls(self):
        a,missing=prepare_mediation(PLAN,DATA);self.assertEqual(missing,['聚类字段'])
        partial={**PLAN,'continue_previous':True,'method':'unspecified','outcome':'','exposure':'','mediators':[],'controls_specified':False,'fixed_effects':[],'se_type':'unspecified','cluster':'firm'}
        b,missing=prepare_mediation(partial,DATA,a);self.assertEqual(missing,[]);self.assertEqual(b['controls'],[])
        c,missing=prepare_mediation({**partial,'continue_previous':False},DATA,a);self.assertIn('中介方法',missing)
        _,missing=prepare_mediation({**PLAN,'controls_specified':False},DATA);self.assertIn('控制变量（也可以指定不加）',missing)

    def test_follow_up_executes_once_and_preview_confirmation_skips_model(self):
        calls=[]
        class Client:
            def __init__(self,**kw):pass
            async def close(self):pass
        class Session:
            def __init__(self,*a,**kw):pass
            async def start(self,instructions,message):
                calls.append(message)
                if message=='中介绕过工具':
                    code='reghdfe m x, absorb(firm year) vce(cluster firm)\npredict m_hat if e(sample)\nreghdfe y m_hat, absorb(firm year) vce(cluster firm)'
                    return SimpleNamespace(id='x',status='tool_calls',calls=[SimpleNamespace(name='run_stata',arguments=json.dumps({'code':code}),call_id='r')])
                if message=='补充聚类':
                    assert '当前待续中介方案' in instructions
                    args={**PLAN,'continue_previous':True,'method':'unspecified','outcome':'','exposure':'','mediators':[],'controls_specified':False,'fixed_effects':[],'se_type':'unspecified','cluster':'firm'}
                elif message=='先预览':args={**PLAN,'intent':'preview','cluster':'firm'}
                else:args=PLAN
                return SimpleNamespace(id='x',status='tool_calls',calls=[SimpleNamespace(name='prepare_mediation_task',arguments=json.dumps(args),call_id='c')])
            async def resume(self,response,outputs):
                assert 'prepare_mediation_task' in outputs[0]['output']
                return SimpleNamespace(id='x',status='tool_calls',calls=[SimpleNamespace(name='prepare_mediation_task',arguments=json.dumps({**PLAN,'cluster':'firm'}),call_id='c')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=ROOT) as path:
            tmp=Path(path).resolve();stata=tmp/'stata.exe';stata.write_text('')
            execute=AsyncMock(return_value={'event':{'tool':'run_mediation','error':False,'mediation_report':{}},'artifacts':[],'report':{}})
            patches=[patch.object(app,'RUNS',tmp/'runs'),patch.object(app,'RAW_MANIFEST',tmp/'raw'/'manifest.json'),patch.object(app,'STATA',str(stata)),patch.object(app.shutil,'which',return_value='uv'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app,'execute_mediation',execute),patch.dict(app.workspace,{'dataset':DATA,'path':None,'loaded':True,'dataset_revision':'r1','messages':[],'events':[],'artifacts':[],'chat_history':[],'response_id':None,'response_model':None,'mediation_draft':None},clear=False),patch.dict(app.settings,{'api_key':'fake','model':'fake','provider':'deepseek','base_url':'https://example.test'},clear=False)]
            for p in patches:p.start()
            try:
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as c:
                    headers={'Origin':'http://127.0.0.1:8765'}
                    def send(msg):return c.post('/api/chat',headers=headers,json={'message':msg}).json()
                    self.assertIn('聚类字段',send('运行中介')['answer']);self.assertEqual(execute.await_count,0)
                    self.assertIn('已完成',send('补充聚类')['answer']);self.assertEqual(execute.await_count,1);self.assertEqual(execute.await_args.args[0]['cluster'],'firm')
                    self.assertIn('尚未执行',send('先预览')['answer']);self.assertEqual(execute.await_count,1)
                    self.assertIn('已完成',send('确认')['answer']);self.assertEqual(execute.await_count,2);self.assertNotIn('确认',calls)
                    self.assertIn('尚未执行',send('先预览')['answer'])
                    app.workspace['dataset_revision']='r2'
                    self.assertIn('聚类字段',send('确认')['answer']);self.assertEqual(execute.await_count,2)
                    self.assertIn('已完成',send('中介绕过工具')['answer']);self.assertEqual(execute.await_count,3)
            finally:
                for p in reversed(patches):p.stop()
