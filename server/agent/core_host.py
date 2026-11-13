"""Bind the shared CIEL persona, permitted memory and conversation to external clients."""
from aiohttp import web
import json
import time
import uuid
import debug_log
from livekit.agents import llm
import models
import mind
from ciel_core import CielCore


class CoreHost:
    def __init__(self, agent, book, *, record=debug_log.record):
        self.agent, self.book = agent, book
        self.record = record
        self.core = CielCore()
        self.runner = None
        self.client = models.create_client('mind')
        self.execution_instructions = agent.persona.execution_instructions

    async def context(self):
        a = self.agent
        style = a.style
        private = style is None or style.presence in ('solo', 'close')
        memory = await self.book.greeting_context(private) if self.book else ''
        context = [{'role':'system','content':a.instructions_for(
            style.talk if style else 'normal', style.presence if style else 'solo', execution=True) + '\n' + self.execution_instructions}]
        # Read the same history without consuming voice notifications or pending notes.
        for turn in a.mind._recent(mind.DEEP_TURNS):
            context.append({'role': 'assistant' if turn.role == 'assistant' else 'user',
                'content': turn.text[:mind.TURN_CHARS] if turn.role == 'assistant' else
                json.dumps({'type':turn.role,'name':turn.name,'text':turn.text[:mind.TURN_CHARS]},ensure_ascii=False)})
        if memory:
            context.append({'role':'user','content':json.dumps({'type':'permitted_memory','text':memory},ensure_ascii=False)})
        return context

    async def infer(self, context, messages, *, response_format='text', max_tokens=256, purpose='game_core',
                    queued_seconds=0):
        context.extend(messages)
        if models.is_local('mind'):
            source = llm.ChatContext()
            for message in context:
                source.add_message(role=message['role'], content=message['content'])
            context = [{'role': item.role, 'content': item.text_content}
                       for item in mind.local_context(source).items]
        ident, began = uuid.uuid4().hex, time.monotonic()
        self.record('core_request', role=purpose, id=ident, model=models.model('mind'),
                         input_chars=sum(len(m['content']) for m in context), queued_seconds=queued_seconds)
        try:
            options = models.options('mind', model=models.model('mind'), messages=context, max_tokens=max_tokens, temperature=0)
            if response_format == 'json':
                options['response_format'] = {'type':'json_object'}
            response = await self.client.chat.completions.create(**options)
            models.record('mind', models.model('mind'), getattr(response, 'usage', None))
            return response.choices[0].message.content or ''
        finally:
            self.record('model_response', role=purpose, id=ident, seconds=round(time.monotonic()-began,3))

    async def start(self):
        token = self.core.bind(context=self.context, infer=self.infer)
        self.runner = web.AppRunner(self.core.application(), access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        return f'http://127.0.0.1:{port}', token

    async def close(self):
        if self.runner: await self.runner.cleanup()
        await self.client.close()
