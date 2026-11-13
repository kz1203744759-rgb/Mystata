import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app
from workspace_cleanup import cleanup_project


class CleanupFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.root=Path(self.tmp.name).resolve()
        for name in ['runs/job','datasets/raw','.stata-tmp','frontend']:
            (self.root/name).mkdir(parents=True,exist_ok=True)
        self.seed={'runs/job/work.do':'commands','runs/job/result.dta':'output',
                   'runs/job/step.log':'log','datasets/raw/upload.dta':'source',
                   'datasets/raw/manifest.json':'[]','.stata-tmp/session.smcl':'log',
                   'app.py':'application','frontend/main.jsx':'frontend'}
        for name,content in self.seed.items():(self.root/name).write_text(content,encoding='utf-8')

    def tearDown(self):self.tmp.cleanup()

    def test_only_uploaded_data_and_run_files_are_removed(self):
        result=cleanup_project(self.root)
        self.assertEqual(result['removed_files'],6)
        for name in list(self.seed)[:5]:self.assertFalse((self.root/name).exists())
        self.assertFalse((self.root/'.stata-tmp/session.smcl').exists())
        self.assertTrue((self.root/'app.py').exists())
        self.assertTrue((self.root/'frontend/main.jsx').exists())

    def test_reparse_point_aborts_before_any_file_deletion(self):
        blocked=self.root/'runs/job/work.do'
        import workspace_cleanup
        original=workspace_cleanup._reparse
        with patch.object(workspace_cleanup,'_reparse',side_effect=lambda path: path==blocked or original(path)):
            with self.assertRaises(ValueError):cleanup_project(self.root)
        self.assertTrue((self.root/'datasets/raw/upload.dta').exists())
        self.assertTrue((self.root/'runs/job/result.dta').exists())

    def test_upgrade_snapshot_is_only_temporarily_kept_and_sanitized(self):
        snapshot=self.root/'runs'/('upgrade-session-'+'a'*32+'.json')
        snapshot.write_text(json.dumps({'messages':[{'role':'user','content':'history'}],'dataset':None,
                                        'active_path':'old.dta','events':[{'old':1}],'artifacts':[{'old':1}]}),encoding='utf-8')
        cleanup_project(self.root,preserve_snapshot=str(snapshot))
        saved=json.loads(snapshot.read_text(encoding='utf-8'))
        self.assertEqual(saved['messages'][0]['content'],'history')
        self.assertIsNone(saved['active_path'])
        self.assertEqual(saved['events'],[])
        self.assertEqual(saved['artifacts'],[])
        self.assertFalse((self.root/'runs/job/work.do').exists())

    def test_startup_command_clears_synthetic_project(self):
        env=os.environ.copy();env.pop('ECONAGENT_SESSION_RESTORE',None)
        result=subprocess.run([sys.executable,str(ROOT/'workspace_cleanup.py'),'--project-dir',str(self.root),'--startup'],
                              capture_output=True,text=True,env=env)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'datasets/raw/upload.dta').exists())
        self.assertFalse((self.root/'runs/job/result.dta').exists())
        self.assertTrue((self.root/'app.py').exists())


class FakeWorker:
    stopped=0
    async def stop(self):self.stopped+=1


class CleanupApiTest(unittest.TestCase):
    def test_clear_resets_workspace_without_clearing_key_or_conversation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root=Path(tmp).resolve()
            (root/'runs/job').mkdir(parents=True);(root/'runs/job/result.do').write_text('x')
            (root/'datasets/raw').mkdir(parents=True);(root/'datasets/raw/upload.dta').write_text('x')
            fake=FakeWorker()
            with patch.object(app,'ROOT',root),patch.object(app,'worker',fake):
                app.settings.update(api_key='fake-key',model='fake',provider='deepseek',base_url='https://api.deepseek.com')
                app.workspace.update(dataset={'filename':'active'},path='old',loaded=True,messages=[{'role':'user','content':'hello'}],events=[{'label':'old'}],artifacts=[{'name':'old'}],chat_history=[{'role':'user','content':'old'}],response_id='r',response_model='fake')
                client=TestClient(app.app,base_url='http://127.0.0.1:8765')
                forbidden=client.post('/api/workspace/clear',headers={'Origin':'https://foreign.example'})
                self.assertEqual(forbidden.status_code,403)
                self.assertTrue((root/'runs/job/result.do').exists())
                result=client.post('/api/workspace/clear',headers={'Origin':'http://127.0.0.1:8765'})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(fake.stopped,1)
                self.assertFalse((root/'datasets/raw/upload.dta').exists())
                self.assertFalse((root/'runs/job/result.do').exists())
                self.assertFalse(app.workspace['loaded'])
                self.assertEqual(app.workspace['events'],[])
                self.assertEqual(app.workspace['artifacts'],[])
                self.assertEqual(app.workspace['chat_history'],[])
                self.assertEqual(app.workspace['messages'][0]['content'],'hello')
                self.assertEqual(app.settings['api_key'],'fake-key')

    def test_busy_workspace_rejects_clear(self):
        lock=type('Locked',(),{'locked':lambda self:True})()
        with patch.object(app,'execution_lock',lock):
            client=TestClient(app.app,base_url='http://127.0.0.1:8765')
            result=client.post('/api/workspace/clear',headers={'Origin':'http://127.0.0.1:8765'})
            self.assertEqual(result.status_code,409)


if __name__=='__main__':unittest.main()
