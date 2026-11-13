import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from fastapi.testclient import TestClient
import httpx
from openai import AsyncOpenAI

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app
from model_clients import ModelSession


class Stream:
    def __init__(self,events): self.events=events;self.closed=False
    def __aiter__(self): return self.iter()
    async def iter(self):
        for event in self.events: yield event
    async def close(self): self.closed=True


def chunk(content=None,reasoning=None,calls=None,finish=None):
    return NS(choices=[NS(delta=NS(content=content,reasoning_content=reasoning,tool_calls=calls),finish_reason=finish)])


class StreamingModelTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_sdk_decodes_chat_stream(self):
        def handler(request):
            self.assertTrue(json.loads(request.content)['stream'])
            def frame(delta,finish=None):
                return 'data: '+json.dumps({'id':'x','object':'chat.completion.chunk','created':1,'model':'x','choices':[{'index':0,'delta':delta,'finish_reason':finish}]},ensure_ascii=False)+'\n\n'
            payload=frame({'role':'assistant','reasoning_content':'hidden'})+frame({'content':'你'})+frame({'content':'好'},'stop')+'data: [DONE]\n\n'
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content=payload.encode())
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client=AsyncOpenAI(api_key='fake',base_url='https://example.test',http_client=http)
        session=ModelSession(client,'deepseek','test',[]);events=[];session.on_event=events.append
        try:
            result=await session.start('system','question')
            self.assertEqual(result.text,'你好')
            self.assertEqual(session.completed_history()[-1]['reasoning_content'],'hidden')
            self.assertEqual([x['text'] for x in events if x['type']=='delta'],['你','好'])
        finally: await client.close()

    async def test_deepseek_stream_accumulates_fragmented_tool_and_thinking(self):
        first=Stream([chunk(reasoning='hidden'),chunk(calls=[NS(index=0,id='call1',function=NS(name='run_stata',arguments='{"code":'))]),
                      chunk(calls=[NS(index=0,id=None,function=NS(name=None,arguments='"display 1"}'))],finish='tool_calls')])
        second=Stream([chunk(content='已'),chunk(content='完成',finish='stop')]);seen=[]
        class Completions:
            async def create(self,**kwargs):
                seen.append(kwargs.copy());return first if len(seen)==1 else second
        client=NS(chat=NS(completions=Completions()))
        session=ModelSession(client,'deepseek','test',[{'name':'run_stata','description':'x','parameters':{}}]);events=[];session.on_event=events.append
        response=await session.start('instruction','question')
        self.assertEqual(response.calls[0].arguments,'{"code":"display 1"}')
        final=await session.resume(response,[{'call_id':'call1','output':'ok'}])
        self.assertEqual(final.text,'已完成')
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),'已完成')
        self.assertEqual(seen[1]['messages'][2]['reasoning_content'],'hidden')
        self.assertTrue(first.closed and second.closed)

    async def test_responses_stream_uses_completed_tool_items(self):
        completed=NS(id='response1',status='completed',output_text='你好',output=[])
        stream=Stream([NS(type='response.output_text.delta',delta='你'),NS(type='response.output_text.delta',delta='好'),NS(type='response.completed',response=completed)])
        class Responses:
            async def create(self,**kwargs):
                assert kwargs['stream'] is True
                return stream
        session=ModelSession(NS(responses=Responses()),'openai','test',[]);events=[];session.on_event=events.append
        result=await session.start('instruction','question')
        self.assertEqual(result.text,'你好')
        self.assertEqual([e['text'] for e in events if e['type']=='delta'],['你','好'])
        self.assertTrue(stream.closed)

    async def test_truncated_stream_is_failure(self):
        class Completions:
            async def create(self,**kwargs): return Stream([chunk(content='partial')])
        session=ModelSession(NS(chat=NS(completions=Completions())),'deepseek','test',[]);session.on_event=lambda e:None
        with self.assertRaisesRegex(RuntimeError,'未完整结束'):await session.start('s','q')


class StreamingEndpointTest(unittest.TestCase):
    def test_endpoint_streams_text_then_complete_result(self):
        class Client:
            def __init__(self,**kwargs):pass
            async def close(self):pass
        class Session:
            def __init__(self,*args,**kwargs):self.on_event=None
            async def start(self,*args):
                self.on_event({'type':'round_start'});self.on_event({'type':'delta','text':'甲'});self.on_event({'type':'delta','text':'乙'})
                return NS(status='completed',calls=[],text='甲乙',id=None)
            def completed_history(self):return []
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,'RUNS',Path(tmp)),patch.object(app,'read_raw',return_value={}),patch.object(app,'AsyncOpenAI',Client),patch.object(app,'ModelSession',Session):
            app.settings.update(api_key='fake',model='test',provider='deepseek',base_url='https://example.test')
            app.workspace.update(dataset=None,path=None,messages=[],events=[],artifacts=[],response_id=None,response_model=None,chat_history=[],loaded=False)
            client=TestClient(app.app,base_url='http://127.0.0.1:8765')
            response=client.post('/api/chat/stream',headers={'Origin':'http://127.0.0.1:8765'},json={'message':'你好'})
            self.assertEqual(response.status_code,200)
            events=[json.loads(line) for line in response.text.splitlines()]
            self.assertEqual([e['type'] for e in events],['round_start','delta','delta','done'])
            self.assertEqual(events[-1]['result']['answer'],'甲乙')
            self.assertEqual(app.workspace['messages'][-1]['content'],'甲乙')

