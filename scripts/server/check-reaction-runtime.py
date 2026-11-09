#!/usr/bin/env python3
"""Offline integration: actual pipeline, reaction scheduler, work notice and audio gate."""
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server' / 'agent'))
os.environ['CIEL_MODEL'] = 'pipeline'
os.environ['CIEL_VOICE'] = 'irodori'

from livekit.agents import Agent, llm
from agent import Ciel
from conversation import Conversation
from mind import Mind
from mouth import Mouth
from tools import State


class Speech:
    def __init__(self, identifier):
        self.id, self.num_steps, self.interrupted = identifier, 1, False
        self.done = asyncio.get_running_loop().create_future()

    def __await__(self):
        return asyncio.shield(self.done).__await__()

    def interrupt(self, *, force=False):
        self.interrupted = True
        if not self.done.done():
            self.done.set_result(None)


async def main():
    agent = Ciel()
    agent.mind = Mind(Conversation())
    report = Mock(return_value='work result')
    agent.mind.goals = Obj(notice=object(), report=report, context=lambda: None, body_step=lambda: False)
    state = State(history=Conversation())
    session = Obj(userdata=state, current_speech=None, agent_state='listening', user_state='listening')
    voice = state.mouth = Mouth(session)
    voice.before_say = agent.mind.on_say
    output, tasks = [], []
    delay = 0.

    async def model_stub(agent, context, functions, settings):
        await asyncio.sleep(delay)
        yield 'pain reaction'

    def generate_reply(**kwargs):
        speech = Speech(str(len(tasks)))
        session.current_speech = speech
        session.agent_state = 'thinking'
        async def run():
            try:
                chat = llm.ChatContext()
                chat.add_message(role='system', content=agent.instructions)
                chat.add_message(role='system', content=kwargs['instructions'])
                chunks = [chunk async for chunk in agent._pipeline_llm(chat, agent.tools, {})]
                output.extend(chunks)
                if chunks:
                    voice.reactions.on_said(Obj(item=Obj(role='assistant', interrupted=False, text_content=''.join(chunks))))
            finally:
                session.agent_state = 'listening'
                if not speech.done.done():
                    speech.done.set_result(None)
        tasks.append(asyncio.create_task(run()))
        return speech

    session.generate_reply = generate_reply
    with patch.object(agent, '_get_activity_or_raise', return_value=Obj(session=session)), \
            patch.object(Agent.default, 'llm_node', model_stub), patch('models.is_local', return_value=False):
        event = voice.react_latest('game', instructions='observed damage', reaction_kind='hurt')
        await asyncio.sleep(.1)
        assert output == ['pain reaction'], output
        assert event.status == 'spoken'
        report.assert_not_called()  # pending work notice must not swallow a damage reaction
        delay = .15
        output.clear()
        envelope = voice.reactions.envelope('game', 'game.damage', {})
        envelope['ttl_ms'] = 40
        expired = voice.reactions.receive('game', envelope, why='game', kwargs={'instructions': 'old damage'})
        await asyncio.sleep(.25)
        assert expired.status == 'expired'
        assert not output
        assert expired.handle.interrupted
        session.current_speech = expired.handle
        async def audio():
            yield 'old audio'
        assert [frame async for frame in agent._reaction_audio(audio(), expired.handle.id)] == []
    await voice.reactions.close()
    await asyncio.gather(*tasks)
    print('passed: damage survives pending work notice; expired generation/audio blocked; speech interrupted')


if __name__ == '__main__':
    asyncio.run(main())
