import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app
import research_context


class ResearchContextTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'datasets' / 'raw' / 'panel.dta'
        self.data.parent.mkdir(parents=True)
        self.data.write_bytes(b'fake dataset used only by tests')
        self.db = self.root / '.econagent' / 'context.sqlite3'
        self.previous = copy.deepcopy(app.workspace)
        self.patches = [patch.object(app, 'ROOT', self.root), patch.object(app, 'RUNS', self.root/'runs'),
                        patch.object(app, 'CONTEXT_DB', self.db)]
        for item in self.patches: item.start()
        app.workspace.update(dataset={'filename':'panel.dta','variables':[{'name':'did','type':'float'},
                             {'name':'y','type':'float'}],'preview':[['PRIVATE_ROW']]},
                             loaded=True,path=str(self.data),dataset_revision='revision-1',
                             research_variables={'x':['did'],'y':['y']},confirmed_model=None,messages=[],events=[],artifacts=[])

    async def asyncTearDown(self):
        app.workspace.clear(); app.workspace.update(self.previous)
        for item in reversed(self.patches): item.stop()
        self.tmp.cleanup()

    async def test_save_and_restore_roles_and_only_completed_models(self):
        report={'outcome':'y','explanatory_variables':['did'],'controls':[],'fixed_effects':[['id']],
                'se_type':'cluster','cluster':'id','dataset_revision':'revision-1','coefficients':[]}
        app.workspace['events']=[{'tool':'run_fixed_effects','error':False,'fixed_effects_report':report},
                                 {'tool':'run_fixed_effects','error':True,'fixed_effects_report':{'outcome':'wrong'}}]
        app.save_research_context()
        saved = research_context.load(self.db)
        self.assertEqual(saved['research_variables']['x'], ['did'])
        self.assertEqual(len(saved['models']), 1)
        self.assertNotIn('PRIVATE_ROW', str(saved))
        self.assertNotIn('api_key', str(saved))
        app.workspace.update(dataset=None,loaded=False,path=None,research_variables={},events=[],messages=[])
        worker=SimpleNamespace(call=AsyncMock(return_value=SimpleNamespace(isError=False,structuredContent={'result':{'success':True,'data':{}}})))
        info={'filename':'panel.dta','variables':[{'name':'did','type':'float'},{'name':'y','type':'float'}]}
        with patch.object(app,'worker',worker), patch.object(app,'inspect_dataset',return_value=info), patch.object(app,'sync_active_dataset',new=AsyncMock()):
            await app.restore_research_context()
        self.assertTrue(app.workspace['loaded'])
        self.assertEqual(app.current_research_variables()['x'],['did'])
        self.assertEqual(app.workspace['dataset_revision'],'revision-1')
        self.assertEqual(len(app.workspace['events']),1)
        worker.call.assert_awaited_once()

    async def test_changed_file_is_not_loaded_and_old_results_remain(self):
        app.workspace['events']=[{'tool':'run_fixed_effects','error':False,'fixed_effects_report':{'outcome':'y'}}]
        app.save_research_context()
        self.data.write_bytes(b'changed dataset')
        app.workspace.update(dataset=None,loaded=False,path=None,research_variables={},events=[],messages=[])
        worker=SimpleNamespace(call=AsyncMock())
        with patch.object(app,'worker',worker):
            await app.restore_research_context()
        self.assertFalse(app.workspace['loaded'])
        self.assertEqual(len(app.workspace['events']),1)
        worker.call.assert_not_awaited()
        self.assertIn('重新挂载',app.workspace['messages'][-1]['content'])

    async def test_memory_only_state_does_not_reopen_old_file(self):
        app.workspace['dataset']['memory_only']=True
        app.save_research_context()
        saved=research_context.load(self.db)
        self.assertIsNone(saved['dataset']['path'])
        self.assertTrue(saved['dataset']['memory_only'])

    async def test_clear_deletes_saved_context_record(self):
        app.save_research_context()
        research_context.clear(self.db)
        self.assertIsNone(research_context.load(self.db))

    async def test_interrupted_model_is_not_reported_as_completed(self):
        app.workspace['confirmed_model']={'type':'fixed_effects','status':'running',
            'dataset_revision':'revision-1','spec':{'outcome':'y','explanatory_variables':['did']}}
        app.save_research_context()
        app.workspace.update(dataset=None,loaded=False,path=None,events=[],messages=[])
        worker=SimpleNamespace(call=AsyncMock(return_value=SimpleNamespace(isError=False,structuredContent={'result':{'success':True,'data':{}}})))
        info={'filename':'panel.dta','variables':[{'name':'did','type':'float'},{'name':'y','type':'float'}]}
        with patch.object(app,'worker',worker), patch.object(app,'inspect_dataset',return_value=info), patch.object(app,'sync_active_dataset',new=AsyncMock()):
            await app.restore_research_context()
        self.assertEqual(app.workspace['confirmed_model']['status'],'interrupted')
        self.assertEqual(app.workspace['events'],[])


if __name__ == '__main__': unittest.main()
