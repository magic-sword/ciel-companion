"""Bind the shared CIEL persona, permitted memory and conversation to external clients."""
from aiohttp import web
import json
from livekit.agents import llm
import models
import mind
from ciel_core import CielCore


class CoreHost:
    def __init__(self, agent, book):
        self.agent, self.book = agent, book
        self.core = CielCore()
        self.runner = None
        self.client = models.create_client('mind')

    async def context(self):
        a = self.agent
        style = a.style
        private = style is None or style.presence in ('solo', 'close')
        memory = await self.book.greeting_context(private) if self.book else ''
        context = [{'role':'system','content':a.instructions_for(
            style.talk if style else 'normal', style.presence if style else 'solo')}]
        # Read the same history without consuming voice notifications or pending notes.
        for turn in a.mind._recent(mind.DEEP_TURNS):
            context.append({'role': 'assistant' if turn.role == 'assistant' else 'user',
                'content': turn.text[:mind.TURN_CHARS] if turn.role == 'assistant' else
                json.dumps({'type':turn.role,'name':turn.name,'text':turn.text[:mind.TURN_CHARS]},ensure_ascii=False)})
        if memory:
            context.append({'role':'user','content':json.dumps({'type':'permitted_memory','text':memory},ensure_ascii=False)})
        return context

    async def infer(self, context, messages):
        context.extend(messages)
        if models.is_local('mind'):
            source = llm.ChatContext()
            for message in context:
                source.add_message(role=message['role'], content=message['content'])
            context = [{'role': item.role, 'content': item.text_content}
                       for item in mind.local_context(source).items]
        response = await self.client.chat.completions.create(**models.options(
            'mind', model=models.model('mind'), messages=context, max_tokens=1024))
        return response.choices[0].message.content or ''

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
