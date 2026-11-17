import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, patch

from core_host import CoreHost


class CoreProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_game_inference_uses_provider_compatible_options(self):
        for local in (False, True):
            with self.subTest(local=local):
                create = AsyncMock(return_value=Obj(usage=None,
                    choices=[Obj(message=Obj(content='OK'))]))
                client = Obj(close=AsyncMock(), chat=Obj(completions=Obj(create=create)))
                with patch('core_host.models.create_client', return_value=client), \
                        patch('core_host.models.is_local', return_value=local), \
                        patch('core_host.models.options', side_effect=lambda role, **kw: kw), \
                        patch.dict('os.environ', {'CIEL_MIND_REASONING': 'none'}):
                    host = CoreHost(Obj(persona=Obj(execution_instructions='')), None)
                    try:
                        self.assertEqual(await host.infer([], [{'role': 'user', 'content': 'prepare'}],
                            max_tokens=1, purpose='game_core_prepare'), 'OK')
                    finally:
                        await host.close()
                sent = create.call_args.kwargs
                self.assertEqual(sent['max_completion_tokens'], 1 if local else 256)
                self.assertNotIn('max_tokens', sent)
                if local:
                    self.assertEqual(sent['temperature'], 0)
                    self.assertNotIn('reasoning_effort', sent)
                else:
                    self.assertEqual(sent['reasoning_effort'], 'none')
                    self.assertNotIn('temperature', sent)
