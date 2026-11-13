import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from merge_workflow import merge_preparation_request,preview_message,preview_only_request
from test_agent_rounds import AgentRoundsTest,FakeSession,done,pending


class MergeWorkflowTest(unittest.TestCase):
    def test_routes_merge_but_not_followup_analysis(self):
        self.assertTrue(merge_preparation_request('以 id 和 year 合并三个文件并挂载',['a','b']))
        self.assertFalse(merge_preparation_request('对合并后的数据进行回归',['a','b']))
        self.assertFalse(merge_preparation_request('合并文件',['a']))

    def test_summary_only_claims_preview(self):
        text=preview_message({'keys':['id','year'],'ok':True,'cardinality':'1:1','metrics':{'FINAL_ROWS':12}})
        self.assertIn('预计最终行：12',text)
        self.assertIn('尚未正式合并或挂载',text)

    def test_explicit_preview_does_not_execute(self):
        self.assertTrue(preview_only_request('请以 id 合并预检'))
        self.assertTrue(preview_only_request('先检查映射，不要执行'))
        self.assertFalse(preview_only_request('以 id 和 year 合并三个文件，挂载到主分析集'))
        self.assertFalse(preview_only_request('先预检通过后再执行合并'))


class MergeGuardTest(AgentRoundsTest):
    def test_unverified_merge_cannot_claim_success(self):
        FakeSession.responses=[done('合并已经完成，并成功挂载主分析集。')]
        result=self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'合并这两个文件','selected_file_ids':['file_a','file_b']})
        self.assertEqual(result.status_code,200)
        self.assertIn('没有完成合并预检或挂载',result.json()['answer'])

    def test_model_cannot_run_arbitrary_stata_in_merge_preparation(self):
        FakeSession.responses=[pending('clear all',0),done('请确认文件字段。')]
        result=self.client.post('/api/chat',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'合并两个文件','selected_file_ids':['file_a','file_b']})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.worker.scripts,[])
        self.assertIn('尚未完成合并预检或挂载',result.json()['answer'])

