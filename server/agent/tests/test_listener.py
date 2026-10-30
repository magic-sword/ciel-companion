import types
import unittest
from unittest import mock

import listener


class FakeMinutes:
    def __init__(self, recording=False):
        self.recording = recording
        self.calls = []

    def start(self, lookback, template):
        self.calls.append(('start', template))
        return 'started'

    def finish(self):
        self.calls.append(('finish',))
        return 'finishing'


def reply(content):
    msg = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)


class ListenerTest(unittest.IsolatedAsyncioTestCase):
    def make(self, minutes, answer):
        client = mock.Mock()
        client.chat.completions.create = mock.AsyncMock(return_value=reply(answer))
        return listener.Listener(None, minutes, '耳の指示', client=client), client

    async def test_request_in_the_middle_of_talk_starts_minutes(self):
        minutes = FakeMinutes()
        ear, client = self.make(minutes, '{"action": "start", "to_ciel": true, "template": "meeting"}')
        handled = []
        ear.on_handled = handled.append
        self.assertEqual(await ear.check('あ、そうだ、議事録開始して'), 'start')
        self.assertEqual(minutes.calls, [('start', 'meeting')])
        self.assertEqual(handled, ['あ、そうだ、議事録開始して'])   # 心が同じ頼みを受け直さないように知らせる
        # 言い直しても、続けては動かさない
        self.assertIsNone(await ear.check('議事録開始してね'))
        self.assertEqual(len(minutes.calls), 1)

    async def test_requests_to_others_and_talk_about_minutes_do_nothing(self):
        minutes = FakeMinutes()
        ear, _ = self.make(minutes, '{"action": "start", "to_ciel": false}')
        self.assertIsNone(await ear.check('田中さん、議事録とっといて'))
        ear, _ = self.make(minutes, '{"action": "none"}')
        self.assertIsNone(await ear.check('前回の議事録、読んだ？'))
        self.assertEqual(minutes.calls, [])

    async def test_only_final_transcripts_with_request_words_are_checked(self):
        ear, client = self.make(FakeMinutes(), '{"action": "none"}')
        with mock.patch('asyncio.create_task') as task:
            ear.on_transcribed(types.SimpleNamespace(is_final=False, transcript='議事録開始して'))
            ear.on_transcribed(types.SimpleNamespace(is_final=True, transcript='ポスターは水曜まで'))
            task.assert_not_called()
            ear.on_transcribed(types.SimpleNamespace(is_final=True, transcript='議事録開始して'))
            task.assert_called_once()
            task.call_args.args[0].close()

    async def test_replies_can_wait_until_the_check_is_done(self):
        minutes = FakeMinutes()
        ear, client = self.make(minutes, '{"action": "start", "to_ciel": true}')
        ear.on_transcribed(types.SimpleNamespace(is_final=True, transcript='議事録開始して'))
        await ear.settled(1.0)
        self.assertEqual(minutes.calls, [('start', 'meeting')])
        await ear.settled(1.0)   # 確かめている頼みが無ければ、すぐ戻る

    async def test_finish_and_bad_answers(self):
        minutes = FakeMinutes(recording=True)
        ear, _ = self.make(minutes, '{"action": "finish", "to_ciel": true}')
        self.assertEqual(await ear.check('議事録終わり'), 'finish')
        ear, _ = self.make(minutes, 'not json')
        self.assertIsNone(await ear.check('議事録まとめて'))
        self.assertEqual(minutes.calls, [('finish',)])


if __name__ == '__main__':
    unittest.main()
