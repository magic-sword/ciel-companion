import unittest
from unittest.mock import AsyncMock

from game_env import GameEnv


class GameBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_resource_updates_do_not_announce_ready_before_inference_binding(self):
        for result in ('ready', 'unavailable'):
            with self.subTest(result=result):
                env = GameEnv('fixture', 'http://127.0.0.1:1/mcp')
                env._session = object()
                env.wanted = True
                env.core_endpoint = ('http://127.0.0.1:2', 'fixture')
                env.profile = {'link_tool': 'link', 'inference': {'bind_tool': 'bind'}}
                env.state = {'playing': True}
                env._refresh = AsyncMock(return_value=True)
                states = []
                env.notify = states.append

                async def call(name, args, **kwargs):
                    if name == 'bind':
                        env.publish()  # a state notification while preparation awaits
                        self.assertFalse(env.linked)
                        self.assertFalse(any(s['linked'] for s in states))
                        return {'status': result}
                    return {'status': 'linked' if args['on'] else 'off'}

                env._call = AsyncMock(side_effect=call)
                await env._link_once(True)
                self.assertEqual(env.linked, result == 'ready')
                self.assertEqual(states[-1]['linked'], result == 'ready')
                if result != 'ready':
                    env._call.assert_awaited_with('link', {'on': False})
