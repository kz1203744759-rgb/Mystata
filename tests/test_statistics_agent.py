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
    received_tools=[]
    def __init__(self,client,provider,model,tools,**kwargs):Session.received_tools=tools
    async def start(self,*args):
        return SimpleNamespace(id='one',status='tool_calls',calls=[SimpleNamespace(name='descriptive_correlation',arguments=json.dumps({'variables':['ROE','Pay'],'kinds':['descriptive','correlation']}),call_id='call')])
    def completed_history(self):return []

class StatisticsAgentTest(unittest.TestCase):
    def test_registered_tool_routes_result_to_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stata=root/'stata.exe';stata.touch()
            dataset={'filename':'test.dta','observations':5,'variables':[{'name':'ROE','type':'float'},{'name':'Pay','type':'double'}]}
            report={'variables':['ROE','Pay'],'kinds':['descriptive','correlation']}
            event={'tool':'descriptive_correlation','label':'统计','statistics_report':report,'error':False,'output':'ok','code':''}
            async def execute(spec,record):
                self.assertEqual(spec,{'variables':['ROE','Pay'],'kinds':['descriptive','correlation']})
                self.assertFalse(record)
                return {'event':event,'report':report,'artifacts':[]}
            with patch.object(app,'RUNS',root/'runs'),patch.object(app,'STATA',str(stata)),patch.object(app,'read_raw',return_value={}),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session),patch.object(app.shutil,'which',return_value='uv'),patch.object(app,'execute_statistics',side_effect=execute) as run:
                app.settings.update(api_key='fake',model='fake',provider='deepseek',base_url='https://example.test')
                app.workspace.update(dataset=dataset,path='existing',loaded=True,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[])
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                response=client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'对 ROE 和 Pay 做描述统计和相关性检验'})
                self.assertEqual(response.status_code,200,response.text)
                self.assertIn('已完成',response.json()['answer'])
                self.assertEqual(response.json()['events'][0]['statistics_report'],report)
                self.assertIn('descriptive_correlation',[tool['name'] for tool in Session.received_tools])
                run.assert_awaited_once()
