import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import app
from test_agent_rounds import AgentRoundsTest, FakeSession, done, pending


def call(name,args,index=0):
    return SimpleNamespace(name=name,arguments=json.dumps(args),call_id=f'call-{index}')


class DtaAgentTest(AgentRoundsTest):
    def post(self,message):
        return self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':message,'selected_file_ids':['file_a']})

    def test_calls_delete_tool_and_returns_refreshed_file_index(self):
        args={'target':'raw','file_id':'file_a','variables':['roe']}
        FakeSession.responses=[SimpleNamespace(id='one',status='tool_calls',text='',calls=[call('drop_dta_columns',args)])]
        event={'tool':'drop_dta_columns','error':False,'output':'已删列'}
        with patch.object(app,'execute_dta_change',new=AsyncMock(return_value=(event,'已删除 roe。'))) as execute:
            response=self.post('删除 ROE.dta 中的 roe 字段')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('已删除',response.json()['answer'])
        self.assertEqual(response.json()['raw_files'][0]['filename'],'ROE.dta')
        execute.assert_awaited_once_with(args,undo=False)

    def test_no_action_when_user_says_not_to_delete(self):
        args={'target':'raw','file_id':'file_a','variables':['roe']}
        FakeSession.responses=[SimpleNamespace(id='one',status='tool_calls',text='',calls=[call('drop_dta_columns',args)])]
        with patch.object(app,'execute_dta_change',new=AsyncMock()) as execute:
            response=self.post('不要对 roe 字段进行删除，只介绍方法')
        self.assertEqual(response.status_code,200,response.text)
        execute.assert_not_awaited()

    def test_multiple_files_are_not_silently_partially_modified(self):
        args={'target':'raw','file_id':'file_a','variables':['roe']}
        FakeSession.responses=[SimpleNamespace(id='one',status='tool_calls',text='',calls=[call('drop_dta_columns',args),call('drop_dta_columns',args,1)])]
        with patch.object(app,'preflight_dta_batch',new=AsyncMock(side_effect=ValueError('同一个文件请只提交一次操作。'))), patch.object(app,'execute_dta_change',new=AsyncMock()) as execute:
            response=self.post('删除两个文件的 roe 字段')
        self.assertIn('未修改任何文件',response.json()['answer']);execute.assert_not_awaited()

    def test_model_cannot_choose_unspecified_fields_or_ambiguous_file(self):
        args={'target':'raw','file_id':'file_a','variables':['roe']}
        FakeSession.responses=[SimpleNamespace(id='one',status='tool_calls',text='',calls=[call('drop_dta_columns',args)])]
        with patch.object(app,'execute_dta_change',new=AsyncMock()) as execute:
            response=self.post('删除 ROE.dta 中不需要的字段')
        self.assertIn('请明确说明',response.json()['answer']);execute.assert_not_awaited()
        extra={**self.raw,'file_b':{'filename':'OTHER.dta','path':'unused','format':'dta','observations':1,'variables':[]}}
        with patch.object(app,'read_raw',return_value=extra),patch.object(app,'execute_dta_change',new=AsyncMock()) as execute:
            response=self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'删除 roe 字段','selected_file_ids':['file_a','file_b']})
        self.assertIn('明确指定要操作的文件',response.json()['answer']);execute.assert_not_awaited()

    def test_generic_stata_drop_is_not_used_for_explicit_field_deletion(self):
        FakeSession.responses=[pending('drop roe',0),done('请使用删列工具。')]
        response=self.post('删除 roe 字段')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.worker.scripts,[])
        self.assertIn('drop_dta_columns',FakeSession.outputs[0][0]['output'])


if __name__=='__main__':unittest.main()
