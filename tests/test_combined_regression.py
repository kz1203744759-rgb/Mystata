import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
import app

class CombineRegression(unittest.TestCase):
    def test_chat_composes_only_saved_models_without_stata(self):
        report={'outcome':'y','explanatory_variables':['x'],'controls':['size'],'fixed_effects':[['firm'],['year']],'n':100,'dataset':'data.dta','coefficients':[{'variable':'x','coefficient':.1,'se':.02,'p':.03}]}
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*args,**kwargs):pass
            async def start(self,instructions,message):
                assert '已执行固定效应模型目录' in instructions
                args={'model_numbers':[1,2],'variables':['x'],'control_groups':[{'name':'企业','variables':['size']}]}
                return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='compose_regression_table',arguments=json.dumps(args),call_id='call')])
            def completed_history(self):return []
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            patches=[patch.object(app,'RUNS',Path(tmp)/'runs'),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session)]
            for p in patches:p.start()
            try:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=None,path=None,messages=[],events=[{'fixed_effects_report':report},{'fixed_effects_report':report}],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
                with TestClient(app.app,base_url='http://127.0.0.1:8765') as client:
                    res=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'合并前两个回归','selected_file_ids':['one','two']})
                    self.assertEqual(res.status_code,200,res.text)
                    self.assertEqual(res.json()['events'][0]['combined_regression']['model_numbers'],[1,2])
                    self.assertEqual(res.json()['events'][0]['tool'],'compose_regression_table')
            finally:
                for p in reversed(patches):p.stop()
