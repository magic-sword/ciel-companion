"""ローカル LLM への振り分け（models.py）と、歌を聴くあいだの切り替え（singing.py）"""
import asyncio
import unittest
from unittest import mock

import models
import singing


class RoutingTest(unittest.TestCase):
    def test_explicit_cloud_mind_preserves_local_background_and_options(self):
        with mock.patch.object(models, 'LOCAL_TEST', True), \
             mock.patch.object(models, 'LOCAL_URL', 'http://local.invalid/v1'), \
             mock.patch.object(models, 'LOCAL_ROLES', {'mind', 'thought'}), \
             mock.patch.object(models, 'OPENAI_ROLES', {'mind'}), \
             mock.patch.dict('os.environ', {'CIEL_MIND_MODEL': 'gpt-5.4-mini'}):
            self.assertFalse(models.is_local('mind'))
            self.assertTrue(models.is_local('thought'))
            self.assertEqual(models.model('mind'), 'gpt-5.4-mini')
            self.assertEqual(models.model('thought'), models.LOCAL_MODEL)
            self.assertEqual(models.reply_options('none'), {'model': 'gpt-5.4-mini', 'reasoning_effort': 'none'})
            self.assertEqual(models.options('mind', model='gpt-5.4-mini', timeout=20),
                             {'model': 'gpt-5.4-mini', 'timeout': 20})
            with mock.patch('openai.AsyncOpenAI') as create:
                self.assertIs(models.create_client('mind'), create.return_value)
                create.assert_called_once_with()
            default = object()
            self.assertIs(models.client_for('mind', default), default)

    def test_only_listed_roles_go_local(self):
        with mock.patch.object(models, 'LOCAL_URL', 'http://127.0.0.1:8094/v1'), \
             mock.patch.object(models, 'LOCAL_ROLES', {'thought', 'brief'}), mock.patch.object(models, '_local_client', None):
            self.assertTrue(models.is_local('thought'))
            self.assertFalse(models.is_local('mind'))   # 返事は OpenAI のまま
            self.assertEqual(models.model('thought'), 'local')
            default = object()
            self.assertIs(models.client_for('mind', default), default)
            local = models.client_for('thought', default)
            self.assertIsNot(local, default)
            self.assertEqual(str(local.base_url).rstrip('/'), 'http://127.0.0.1:8094/v1')
            o = models.options('thought', model='gpt-5.4-mini', reasoning_effort='low', timeout=20.0, messages=[])
            self.assertEqual(o['model'], 'local')
            self.assertNotIn('reasoning_effort', o)
            self.assertEqual(o['timeout'], models.LOCAL_TIMEOUT)
            self.assertEqual(o['extra_body'], {'chat_template_kwargs': {'enable_thinking': False}})
            # OpenAI の役目は、そのまま
            self.assertEqual(models.options('mind', model='x', reasoning_effort='low'), {'model': 'x', 'reasoning_effort': 'low'})

    def test_no_url_means_nothing_is_local(self):
        with mock.patch.object(models, 'LOCAL_URL', ''), mock.patch.object(models, 'LOCAL_ROLES', {'thought'}):
            self.assertFalse(models.is_local('thought'))
            self.assertEqual(models.model('thought'), 'gpt-5.4-mini')


class SingingSwitchTest(unittest.IsolatedAsyncioTestCase):
    async def test_song_moves_the_llm_to_cpu_and_back(self):
        listener = singing.SongListener(session=None, tap=None, feedback='')
        modes = []

        async def fake(mode, delay=0.0):
            await asyncio.sleep(delay)
            modes.append(mode)
        listener._http = object()
        with mock.patch.object(listener, '_llm_mode', side_effect=fake), \
             mock.patch.object(singing, 'TTS_RELEASE_URL', 'http://x/release'):
            # 読み上げに GPU を空けてもらう前に、LLM を CPU の形へ（読み上げへの頼みは失敗しても続く）
            with mock.patch.object(listener, '_http', None):
                listener._http = mock.MagicMock()
                listener._http.post.side_effect = RuntimeError('no tts here')
                await listener._release_tts()
            self.assertEqual(modes, ['cpu'])
            # やめたあとの「戻す」は遅らせる。次の歌が始まったら、その「戻す」はやめる
            listener._llm_back(delay=0.05)
            await listener._release_tts()
            await asyncio.sleep(0.1)
            self.assertEqual(modes, ['cpu', 'cpu'])
            listener._llm_back()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertEqual(modes[-1], 'gpu')


if __name__ == '__main__':
    unittest.main()
