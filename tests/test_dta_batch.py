import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app
import dta_changes
from test_agent_rounds import AgentRoundsTest, FakeSession


class BatchEditTest(unittest.TestCase):
    def setUp(self):
        AgentRoundsTest.setUp(self)
        root=Path(self.tmp.name)
        (root/'datasets').mkdir()
        self.files={
            'x':{'filename':'X.dta','path':str(root/'datasets'/'x.dta'),'format':'dta','observations':1,'variables':[{'name':n} for n in ['stkcd','year','ln数字化转型','other']]},
            'y':{'filename':'Y.dta','path':str(root/'datasets'/'y.dta'),'format':'dta','observations':1,'variables':[{'name':n} for n in ['证券简称','省份','城市','区县','行业代码','行业名称','id']]},
        }
        for f in self.files.values():Path(f['path']).touch()
        self.file_patch=patch.object(app,'read_raw',return_value=self.files)
        self.root_patch=patch.object(app,'ROOT',root)
        self.file_patch.start();self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop();self.file_patch.stop()
        AgentRoundsTest.tearDown(self)

    def test_clauses_and_column_selection(self):
        text='删除Y的证券简称、省份、城市、区县、行业代码、行业名称，仅保留X的stkcd、year、ln数字化转型'
        clauses=app.dta_file_clauses(text,self.files)
        self.assertEqual(clauses['y'],'删除Y的证券简称、省份、城市、区县、行业代码、行业名称')
        self.assertEqual(clauses['x'],'仅保留X的stkcd、year、ln数字化转型')
        self.assertEqual(app.mentioned_dta_files('仅保留 X 的stkcd',self.files),['x'])
        self.assertEqual(dta_changes.columns_to_drop(['a','b','c'],['a','c'],'keep'),['b'])
        self.assertEqual(dta_changes.columns_to_drop(['a','b'],['a','b'],'keep'),[])
        with self.assertRaises(ValueError):dta_changes.columns_to_drop(['a'],['missing'],'keep')

    def test_chat_dispatches_each_file_and_preflights_first(self):
        text='删除Y的证券简称、省份、城市、区县、行业代码、行业名称，仅保留X的stkcd、year、ln数字化转型'
        ops=[{'target':'raw','file_id':'y','action':'drop','variables':['证券简称','省份','城市','区县','行业代码','行业名称']},
             {'target':'raw','file_id':'x','action':'keep','variables':['stkcd','year','ln数字化转型']}]
        call=SimpleNamespace(name='edit_dta_columns_batch',arguments=json.dumps({'operations':ops}),call_id='c')
        FakeSession.responses=[SimpleNamespace(id='r',status='tool_calls',text='',calls=[call])]
        def header(path):
            f=next(f for f in self.files.values() if Path(f['path'])==path)
            return {'columns':f['variables'],'observations':1}
        async def execute(op,mode):return {'tool':'edit_dta_columns_batch','error':False,'output':op['file_id']},op['file_id']+' done'
        with patch.object(app,'dta_header',side_effect=header),patch.object(app,'execute_dta_change',new=AsyncMock(side_effect=execute)) as run:
            response=self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':text,'selected_file_ids':['x','y']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('y done',response.json()['answer']);self.assertIn('x done',response.json()['answer'])
        self.assertEqual(run.await_count,2)
        self.assertEqual(run.await_args_list[1].kwargs['mode'],'keep')

    def test_preflight_blocks_everything_if_any_field_is_missing(self):
        text='删除Y的证券简称，仅保留X的stkcd、year、缺失字段'
        ops=[{'target':'raw','file_id':'y','action':'drop','variables':['证券简称']},
             {'target':'raw','file_id':'x','action':'keep','variables':['stkcd','year','缺失字段']}]
        def header(path):
            f=next(f for f in self.files.values() if Path(f['path'])==path)
            return {'columns':f['variables'],'observations':1}
        with patch.object(app,'dta_header',side_effect=header):
            with self.assertRaises(ValueError):asyncio.run(app.preflight_dta_batch(ops,text,['x','y'],[]))

    def test_preflight_does_not_mix_fields_between_files(self):
        text='删除Y的证券简称，仅保留X的stkcd、year'
        ops=[{'target':'raw','file_id':'y','action':'drop','variables':['证券简称']},
             {'target':'raw','file_id':'x','action':'keep','variables':['stkcd','证券简称']}]
        def header(path):
            f=next(f for f in self.files.values() if Path(f['path'])==path)
            return {'columns':f['variables'],'observations':1}
        with patch.object(app,'dta_header',side_effect=header):
            with self.assertRaises(ValueError):
                asyncio.run(app.preflight_dta_batch(ops,text,['x','y'],[]))

    def test_except_clause_requires_full_keep_list(self):
        text='删除X.dta除stkcd、year、ln数字化转型外所有字段'
        self.assertEqual(app.dta_except_keep_fields(text),['stkcd','year','ln数字化转型'])
        op={'target':'raw','file_id':'x','action':'keep','variables':['stkcd','year','ln数字化转型']}
        app.validate_dta_chat_request(op,text,['x'],[],mode='keep')
        with self.assertRaisesRegex(ValueError,'完整匹配'):
            app.validate_dta_chat_request({**op,'variables':['stkcd','year']},text,['x'],[],mode='keep')
        with self.assertRaisesRegex(ValueError,'保留字段操作'):
            app.validate_dta_chat_request({**op,'variables':['other']},text,['x'],[],mode='drop')
        self.assertIsNone(app.dta_except_keep_fields('删除X.dta的stkcd、year字段'))

    def test_wrong_drop_tool_is_corrected_before_edit(self):
        text='删除X.dta除stkcd、year、ln数字化转型外所有字段'
        wrong={'target':'raw','file_id':'x','variables':['other']}
        keep={'target':'raw','file_id':'x','action':'keep','variables':['stkcd','year','ln数字化转型']}
        c1=SimpleNamespace(name='drop_dta_columns',arguments=json.dumps(wrong),call_id='c1')
        c2=SimpleNamespace(name='edit_dta_columns_batch',arguments=json.dumps({'operations':[keep]}),call_id='c2')
        FakeSession.responses=[SimpleNamespace(id='r1',status='tool_calls',text='',calls=[c1]),SimpleNamespace(id='r2',status='tool_calls',text='',calls=[c2])]
        def header(path):return {'columns':self.files['x']['variables'],'observations':1}
        event={'tool':'edit_dta_columns_batch','error':False,'output':'已完成'}
        with patch.object(app,'dta_header',side_effect=header),patch.object(app,'execute_dta_change',new=AsyncMock(return_value=(event,'已完成'))) as execute:
            response=self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':text,'selected_file_ids':['x']})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('已完成',response.json()['answer'])
        self.assertIn('使用保留字段操作',FakeSession.outputs[0][0]['output'])
        execute.assert_awaited_once_with(keep,mode='keep')
