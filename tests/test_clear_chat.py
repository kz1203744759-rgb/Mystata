import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app


class ClearChatTest(unittest.TestCase):
    def test_clears_only_conversation_and_context(self):
        dataset={'filename':'active.dta','observations':2,'variables':[]}
        app.workspace.update(dataset=dataset,path='keep',loaded=True,messages=[{'role':'user','content':'hello'}],
                             chat_history=[{'role':'user','content':'hello'}],response_id='old',response_model='model',
                             events=[{'tool':'etl'}],artifacts=[{'name':'active.dta'}])
        with patch.object(app.worker,'stop',side_effect=AssertionError('must not stop Stata')):
            client=TestClient(app.app,base_url='http://127.0.0.1:8765')
            response=client.post('/api/chat/clear',headers={'Origin':'http://127.0.0.1:8765'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(app.workspace['messages'],[])
        self.assertEqual(app.workspace['chat_history'],[])
        self.assertIsNone(app.workspace['response_id'])
        self.assertIsNone(app.workspace['response_model'])
        self.assertEqual(app.workspace['dataset'],dataset)
        self.assertEqual(app.workspace['path'],'keep')
        self.assertTrue(app.workspace['loaded'])
        self.assertEqual(app.workspace['events'],[{'tool':'etl'}])
        self.assertEqual(app.workspace['artifacts'],[{'name':'active.dta'}])

    def test_rejects_foreign_origin_and_busy(self):
        client=TestClient(app.app,base_url='http://127.0.0.1:8765')
        self.assertEqual(client.post('/api/chat/clear',headers={'Origin':'https://foreign.example'}).status_code,403)
        class Busy:
            def locked(self): return True
        with patch.object(app,'execution_lock',Busy()):
            self.assertEqual(client.post('/api/chat/clear',headers={'Origin':'http://127.0.0.1:8765'}).status_code,409)
