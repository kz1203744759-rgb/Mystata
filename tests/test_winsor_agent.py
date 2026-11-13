import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class Client:
    def __init__(self, **kwargs): pass
    async def close(self): pass


class Session:
    arguments = {}
    def __init__(self, client, provider, model, tools, **kwargs):
        self.tools = tools
    async def start(self, *args):
        return SimpleNamespace(id='one', status='tool_calls', calls=[SimpleNamespace(
            name='winsor2_columns', arguments=json.dumps(self.arguments), call_id='c1')])
    def completed_history(self): return []


class WinsorAgentTest(unittest.TestCase):
    def test_agent_passes_model_interpretation_to_execution(self):
        # These mock the model output; they do not test actual model comprehension.
        cases = [
            ('对roe和pay上下5%缩微不要新变量', 'symmetric', 5, 0, 5, 95),
            ('不要双侧，只缩上侧5%，覆盖', 'upper_tail', 5, 0, 0, 95),
            ('按1和99分位缩尾，覆盖', 'percentiles', 1, 99, 1, 99),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); stata = root / 'stata.exe'; stata.touch()
            dataset = {'filename':'base.dta', 'observations':100, 'variables':[{'name':'ROE'}, {'name':'Pay'}]}
            async def execute(spec, record):
                self.assertEqual((spec['lower'], spec['upper']), expected)
                self.assertEqual(spec['variables'], ['ROE', 'Pay'])
                self.assertEqual(spec['mode'], 'replace')
                return {'dataset':dataset, 'event':{'tool':'winsor2_columns','error':False}, 'artifacts':[],
                        'report':{'lower':spec['lower'],'upper':spec['upper'],'changed':[{'source':'ROE','target':'ROE','rows':1}]}}
            with patch.object(app,'RUNS',root/'runs'), patch.object(app,'STATA',str(stata)), patch.object(app,'read_raw',return_value={}), patch.object(app,'AsyncOpenAI',Client), patch.object(app,'ModelSession',Session), patch.object(app.shutil,'which',return_value='uv'), patch.object(app,'execute_winsor',side_effect=execute) as run:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                client = TestClient(app.app,base_url='http://127.0.0.1:8765')
                for message, kind, p1, p2, low, high in cases:
                    with self.subTest(message=message):
                        expected = (low, high)
                        Session.arguments = {'variables':['roe','pay'],'excluded_variables':[], 'cut_kind':kind,
                                             'p1':p1,'p2':p2,'mode':'replace','suffix':'','scope':'all'}
                        app.workspace.update(dataset=dataset,path='existing',loaded=True,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[])
                        response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':message})
                        self.assertEqual(response.status_code,200,response.text)
                        self.assertIn('缩尾已完成',response.json()['answer'])
                self.assertEqual(run.await_count,3)
                Session.arguments.update(cut_kind='unspecified')
                app.workspace.update(dataset=dataset,path='existing',loaded=True,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[])
                response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'对 ROE 和 Pay 缩尾'})
                self.assertIn('未执行缩尾',response.json()['answer'])
                self.assertEqual(run.await_count,3)
