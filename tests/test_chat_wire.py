import json
import sys
import unittest
from pathlib import Path
import httpx
from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_clients import ModelSession


class ChatWireTest(unittest.IsolatedAsyncioTestCase):
    async def test_deepseek_preserves_tool_calls_and_reasoning(self):
        seen=[]
        def handler(request):
            body=json.loads(request.content)
            seen.append(body)
            assert request.url.host == 'api.deepseek.com'
            assert request.url.path == '/chat/completions'
            assert body['tools'][0]['function']['name'] == 'run_stata'
            if len(seen)==1:
                message={'role':'assistant','content':None,'reasoning_content':'opaque-state',
                    'tool_calls':[{'id':'call-1','type':'function','function':{'name':'run_stata','arguments':'{"code":"display 1"}'}}]}
                finish='tool_calls'
            else:
                assert any(m.get('reasoning_content')=='opaque-state' for m in body['messages'])
                assert any(m.get('role')=='tool' and m.get('tool_call_id')=='call-1' for m in body['messages'])
                message={'role':'assistant','content':'done','reasoning_content':'done-state'}
                finish='stop'
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,
                'model':'deepseek-flash','choices':[{'index':0,'finish_reason':finish,'message':message}]})
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncOpenAI(api_key='fake-key',base_url='https://api.deepseek.com',http_client=http)
        tools=[{'name':'run_stata','description':'run','parameters':{'type':'object','properties':{}}}]
        session=ModelSession(client,'deepseek','deepseek-flash',tools)
        first=await session.start('system','question')
        self.assertEqual(first.calls[0].call_id,'call-1')
        final=await session.resume(first,[{'type':'function_call_output','call_id':'call-1','output':'1'}])
        self.assertEqual(final.text,'done')
        self.assertEqual(session.completed_history()[-1]['reasoning_content'],'done-state')
        await client.close()

if __name__=='__main__': unittest.main()
