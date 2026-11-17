import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app

class Client:
    def __init__(self,**kwargs):pass
    async def close(self):pass

class Session:
    instructions=''
    def __init__(self,*args,**kwargs):pass
    async def start(self,instructions,message):
        Session.instructions=instructions
        return SimpleNamespace(id='one',status='completed',calls=[],text='已记录研究变量。')
    def completed_history(self):return []

class ResearchVariablesTest(unittest.TestCase):
    def setUp(self):
        self.prior=copy.deepcopy(app.workspace)
        self.settings=copy.deepcopy(app.settings)
        app.workspace.update(dataset={'filename':'base.dta','observations':5,'variables':[{'name':'ROE','type':'float','label':'收益率'},{'name':'Pay','type':'double','label':'薪酬'},{'name':'id','type':'long'}]},loaded=True,path='base',messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],research_variables=app.empty_research_variables(),dataset_revision='v1')
        self.client=TestClient(app.app,base_url='http://127.0.0.1:8765')
        self.headers={'Origin':'http://127.0.0.1:8765'}
    def tearDown(self):
        app.workspace.clear();app.workspace.update(self.prior)
        app.settings.clear();app.settings.update(self.settings)
    def post(self,role,values,revision='v1'):
        return self.client.post('/api/research-variables',headers=self.headers,json={'role':role,'variables':values,'dataset_revision':revision})
    def test_roles_support_multiple_and_reject_stale_or_nonexistent_fields(self):
        self.assertEqual(self.post('x',['ROE','Pay']).status_code,200)
        self.assertEqual(self.post('y',['Pay']).status_code,200)
        self.assertEqual(self.post('x',['ROE','missing']).status_code,400)
        self.assertEqual(self.post('x',['ROE'],'old').status_code,409)
        self.assertEqual(self.post('unknown',[]).status_code,400)
        result=self.client.get('/api/workspace').json()
        self.assertEqual(result['research_variables']['x'],['ROE','Pay'])
        self.assertEqual(result['research_variables']['y'],['Pay'])
        self.assertEqual(self.client.post('/api/chat/clear',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/workspace').json()['research_variables']['x'],['ROE','Pay'])
    def test_new_dataset_resets_roles_while_winsor_retains_valid_fields(self):
        self.post('x',['ROE','Pay'])
        smaller={'filename':'winsor.dta','variables':[{'name':'ROE','type':'float'}]}
        app.commit_active(smaller,'out',{'tool':'winsor2_columns'},[])
        self.assertEqual(app.current_research_variables()['x'],['ROE'])
        self.assertNotEqual(app.workspace['dataset_revision'],'v1')
        app.commit_active(smaller,'new',{'tool':'activate_data'},[])
        self.assertEqual(app.current_research_variables()['x'],[])
        self.assertNotEqual(app.workspace['dataset_revision'],'v1')
    def test_agent_gets_assigned_roles_as_context(self):
        self.post('x',['ROE']);self.post('y',['Pay'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stata=root/'stata.exe';stata.touch()
            with patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value={}),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app.shutil,'which',return_value='uv'):
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                result=self.client.post('/api/chat',headers=self.headers,json={'message':'我的研究变量是什么？'})
                self.assertEqual(result.status_code,200,result.text)
                self.assertIn('"x": ["ROE"]',Session.instructions)
                self.assertIn('"y": ["Pay"]',Session.instructions)

    def test_model_suggestions_are_validated_and_do_not_assign_roles(self):
        captured=[]
        class FakeCompletions:
            async def create(self,**kwargs):
                captured.append(kwargs)
                content=json.dumps({'x':[{'name':'ROE','reason':'候选 X'}],'y':[{'name':'Pay','reason':'候选 Y'}],
                    'controls':[{'name':'Pay','reason':'候选控制变量'},{'name':'missing','reason':'不存在'}],
                    'mediators':[{'name':'ROE','reason':'可能中介'}],'moderators':[{'name':'Pay','reason':'可能调节'}],
                    'instruments':[{'name':'id','reason':'可能工具'}]})
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        class FakeClient:
            def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=FakeCompletions())
            async def close(self):pass
        app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
        with patch.object(app,'AsyncOpenAI',FakeClient):
            response=self.client.post('/api/research-variables/suggest',headers=self.headers,json={'dataset_revision':'v1'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([v['name'] for v in response.json()['suggestions']['controls']],['Pay'])
        for role in app.RESEARCH_ROLES:
            self.assertTrue(response.json()['suggestions'][role])
            self.assertEqual(app.current_research_variables()[role],[])
            self.assertIn(role,captured[0]['messages'][0]['content'])
