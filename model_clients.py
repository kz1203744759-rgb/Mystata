"""Provider-specific model tool loops without storing credentials on disk."""
from types import SimpleNamespace


class ModelSession:
    def __init__(self, client, provider, model, tools, previous_id=None, history=None):
        self.client = client
        self.provider = provider
        self.model = model
        self.tools = tools
        self.previous_id = previous_id
        self.history = list(history or [])
        self.messages = None
        self.on_event = None
        self.native = provider == 'openai'
        self.chat_tools = [{'type':'function','function':{
            'name':t['name'], 'description':t['description'], 'parameters':t['parameters']
        }} for t in tools]

    async def start(self, instruction, message):
        self.instruction = instruction
        if self.on_event: self.on_event({'type':'round_start'})
        if self.native:
            options = {'model':self.model,'instructions':instruction,'input':message,
                       'tools':self.tools,'parallel_tool_calls':False}
            if self.previous_id: options['previous_response_id'] = self.previous_id
            response = await self._responses_stream(options) if self.on_event else await self.client.responses.create(**options)
            return self._responses(response)
        self.messages = [{'role':'system','content':instruction}, *self.history,
                         {'role':'user','content':message}]
        return await self._chat()

    async def resume(self, response, outputs):
        if self.on_event: self.on_event({'type':'round_start'})
        if self.native:
            options = dict(model=self.model, instructions=self.instruction,
                previous_response_id=response.id, input=outputs, tools=self.tools, parallel_tool_calls=False)
            raw = await self._responses_stream(options) if self.on_event else await self.client.responses.create(**options)
            return self._responses(raw)
        self.messages.extend({'role':'tool','tool_call_id':item['call_id'],'content':item['output']}
                             for item in outputs)
        return await self._chat()

    def _responses(self, response):
        return SimpleNamespace(id=response.id, status=response.status, text=response.output_text,
                               calls=[c for c in response.output if c.type == 'function_call'])

    async def _responses_stream(self, options):
        stream = await self.client.responses.create(**options, stream=True)
        response = None
        try:
            async for event in stream:
                if event.type == 'response.output_text.delta':
                    self.on_event({'type':'delta','text':event.delta})
                elif event.type in ('response.completed','response.incomplete','response.failed'):
                    response = event.response
                elif event.type == 'error':
                    raise RuntimeError(getattr(event, 'message', '模型流式输出失败。'))
        finally:
            await stream.close()
        if response is None: raise RuntimeError('模型流式输出中断，未收到完整结果。')
        return response

    async def _chat(self):
        if self.on_event: return await self._chat_stream()
        response = await self.client.chat.completions.create(model=self.model, messages=self.messages,
                                                             tools=self.chat_tools)
        if not response.choices: raise RuntimeError('模型没有返回结果。')
        choice = response.choices[0]
        message = choice.message
        raw_calls = message.tool_calls or []
        if not raw_calls and choice.finish_reason != 'stop':
            raise RuntimeError(f'模型响应未完整结束：{choice.finish_reason}')
        # DeepSeek thinking mode requires reasoning_content on subsequent tool requests.
        assistant = {'role':'assistant','content':message.content}
        reasoning = getattr(message, 'reasoning_content', None)
        if reasoning is not None: assistant['reasoning_content'] = reasoning
        if raw_calls:
            assistant['tool_calls'] = [{'id':c.id,'type':'function',
                'function':{'name':c.function.name,'arguments':c.function.arguments}} for c in raw_calls]
        self.messages.append(assistant)
        calls = [SimpleNamespace(name=c.function.name, arguments=c.function.arguments,
                                 call_id=c.id) for c in raw_calls]
        return SimpleNamespace(id=None, status='completed' if not calls else 'tool_calls',
                               text=message.content or '', calls=calls)

    async def _chat_stream(self):
        stream=await self.client.chat.completions.create(model=self.model,messages=self.messages,
                                                         tools=self.chat_tools,stream=True)
        content=[]; reasoning=[]; calls={}; finish=None
        try:
            async for chunk in stream:
                for choice in chunk.choices:
                    delta=choice.delta
                    if delta.content:
                        content.append(delta.content)
                        self.on_event({'type':'delta','text':delta.content})
                    thought=getattr(delta,'reasoning_content',None)
                    if thought is not None: reasoning.append(thought)
                    for call in delta.tool_calls or []:
                        item=calls.setdefault(call.index,{'id':'','name':'','arguments':''})
                        if call.id: item['id']+=call.id
                        if call.function:
                            if call.function.name: item['name']+=call.function.name
                            if call.function.arguments: item['arguments']+=call.function.arguments
                    if choice.finish_reason: finish=choice.finish_reason
        finally:
            await stream.close()
        if finish not in ('stop','tool_calls'):
            raise RuntimeError(f'模型流式输出未完整结束：{finish or "连接中断"}')
        if finish=='tool_calls' and not calls: raise RuntimeError('模型未完整返回工具调用。')
        ordered=[calls[k] for k in sorted(calls)]
        if any(not c['id'] or not c['name'] for c in ordered): raise RuntimeError('模型工具调用信息不完整。')
        assistant={'role':'assistant','content':''.join(content) or None}
        if reasoning: assistant['reasoning_content']=''.join(reasoning)
        if ordered:
            assistant['tool_calls']=[{'id':c['id'],'type':'function','function':{'name':c['name'],'arguments':c['arguments']}} for c in ordered]
        self.messages.append(assistant)
        return SimpleNamespace(id=None,status='tool_calls' if ordered else 'completed',text=''.join(content),
            calls=[SimpleNamespace(name=c['name'],arguments=c['arguments'],call_id=c['id']) for c in ordered])

    def completed_history(self):
        return [] if self.native else self.messages[1:]
