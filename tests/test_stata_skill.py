"""Project-skill wiring and simulated scenarios; no real model or Stata."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app


class FakeModel:
    calls=[]
    answer=''
    async def create(self, **kwargs):
        messages=kwargs['messages']
        self.calls.append(messages)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=self.answer,reasoning_content=None,tool_calls=None),finish_reason='stop')])


class FakeClient:
    def __init__(self, **_): self.chat=SimpleNamespace(completions=FakeModel())
    async def close(self): pass


class SkillWiringTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
        root=Path(self.tmp.name)
        self.patches=[patch.object(app,'RUNS',root/'runs'),patch.object(app,'RAW',root/'raw'),
                      patch.object(app,'RAW_MANIFEST',root/'raw'/'manifest.json'),
                      patch.object(app,'AsyncOpenAI',FakeClient)]
        for p in self.patches:p.start()
        app.settings.update(api_key='test-key',model='test-model',provider='deepseek',base_url='https://example.test')
        app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
        FakeModel.calls=[]
        self.client=TestClient(app.app,base_url='http://127.0.0.1:8765')
        self.headers={'Origin':'http://127.0.0.1:8765'}

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def upload(self,left,right):
        response=self.client.post('/api/raw-files',headers=self.headers,files=[
            ('files',('left.csv',left.encode(),'text/csv')),
            ('files',('right.csv',right.encode(),'text/csv'))])
        self.assertEqual(response.status_code,200,response.text)

    def chat(self,message):
        with patch.object(app.Path,'is_file',return_value=True),patch.object(app.shutil,'which',return_value='uv'):
            result=self.client.post('/api/chat',headers=self.headers,json={'message':message})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def test_confirmed_stock_code_mapping_scenario(self):
        self.upload('Stkcd,year,value\n000002,2022,10\n','stock_code,year,cost\n000002,2022,1\n')
        FakeModel.answer='已知两列使用同一编码；检查键唯一性与转换后碰撞，再生成合并计划。尚未执行合并。'
        result=self.chat('两份证券代码经数据说明确认属于同一编码，请检查并准备合并。')
        system=FakeModel.calls[-1][0]['content']
        self.assertIn('证券代码与数据库内部企业 ID 不是同一编码',system)
        self.assertIn('left.csv',system)
        self.assertIn('right.csv',system)
        self.assertNotIn('000002',system)
        self.assertIn('尚未执行',result['answer'])
        self.assertFalse(result['loaded'])

    def test_patent_years_are_not_equivalent_scenario(self):
        self.upload('stock_code,apply_year\n000002,2021\n','stock_code,grant_year\n000002,2022\n')
        FakeModel.answer='申请年和授权年是不同时间口径；请确定研究需要哪个年份，再继续合并。'
        result=self.chat('按企业和年份合并专利申请表与授权表。')
        system=FakeModel.calls[-1][0]['content']
        self.assertIn('专利申请年、公开年、授权年是不同事件',system)
        self.assertIn('不得自动对齐',system)
        self.assertIn('请确定',result['answer'])
        self.assertFalse(result['loaded'])


if __name__=='__main__':unittest.main()
