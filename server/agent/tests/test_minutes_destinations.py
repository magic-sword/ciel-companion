"""Where the minutes go: destinations registered on each app device, switched from the app or by voice (minutes.py)."""
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from livekit import rtc

from conversation import Conversation
import minutes
from tools.minutes import choose_minutes_destination

WORK = 'https://discord.com/api/webhooks/123456/work-token_1'
HOME = 'https://discordapp.com/api/webhooks/987654/home-token'


def packet(msg):
    p = Mock(spec=rtc.DataPacket)
    p.topic, p.data = minutes.TOPIC, json.dumps(msg).encode('utf-8')
    return p


class DestinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('minutes.openai.AsyncOpenAI', Mock()), ('minutes.WEBHOOK', ''),
                              ('minutes.SAVE_DIR', Path(self.tmp.name))]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.h = Conversation()
        self.m = minutes.Minutes(None, 'test instructions', self.h)
        self.m._summarize = AsyncMock(return_value=None)
        self.context = Mock()
        self.context.userdata.minutes = self.m

    def register(self, selected='仕事'):
        self.m.on_data(packet({'v': 1, 'type': 'minutes.control', 'action': 'destinations', 'selected': selected,
                               'items': [{'name': '仕事', 'url': WORK}, {'name': '家族', 'url': HOME}]}))

    async def meeting(self):
        self.m.start()
        for text in ('first', 'second'):
            self.h.complete(self.h.reserve(time.time()), text)
        self.m.finish()
        await asyncio.gather(*self.m._tasks)

    async def test_sends_to_the_selected_device_destination(self):
        self.register(selected='家族')
        with patch('minutes.WEBHOOK', 'https://discord.com/api/webhooks/1/default'), \
                patch('minutes.post_discord') as post:
            await self.meeting()
        self.assertEqual(post.call_args.args[0], HOME)
        latest = self.m.status()['latest_export']
        self.assertEqual((latest['stage'], latest['destination']), ('sent', '家族'))
        self.assertIn('"destination": "家族"', self.m.context())

    async def test_without_device_destinations_the_server_default_is_used(self):
        with patch('minutes.WEBHOOK', 'https://discord.com/api/webhooks/1/default'), \
                patch('minutes.post_discord') as post:
            await self.meeting()
        self.assertEqual(post.call_args.args[0], 'https://discord.com/api/webhooks/1/default')
        self.assertEqual(self.m.status()['latest_export']['destination'], minutes.DEFAULT_DESTINATION)

    async def test_without_any_destination_it_is_saved_on_the_server(self):
        with patch('minutes.post_discord') as post:
            await self.meeting()
        post.assert_not_called()
        self.assertEqual(self.m.status()['latest_export']['stage'], 'saved_locally')
        self.assertIsNone(self.m.status()['destination'])

    def test_only_discord_webhooks_are_accepted(self):
        self.m.set_destinations([
            {'name': '内側', 'url': 'http://127.0.0.1:8080/api/webhooks/1/x'},
            {'name': '偽物', 'url': 'https://discord.com.evil.example/api/webhooks/1/x'},
            {'name': '後ろ', 'url': WORK + '/../../other'},
            {'name': '', 'url': WORK},
            {'name': 'x' * 31, 'url': WORK},
            'not a dict',
            {'name': ' 仕事 ', 'url': WORK},
            {'name': '仕事', 'url': HOME},   # 同じ名前は先のものだけ
        ], selected=['not', 'a', 'name'])
        self.assertEqual(self.m.destinations, {'仕事': WORK})
        self.assertEqual(self.m.destination, '仕事')

    def test_too_many_are_cut_and_a_missing_selection_falls_back_to_the_first(self):
        self.m.set_destinations([{'name': f'ch{i}', 'url': WORK} for i in range(15)], selected='消した')
        self.assertEqual(len(self.m.destinations), minutes.MAX_DESTINATIONS)
        self.assertEqual(self.m.destination, 'ch0')
        self.m.set_destinations([], selected='ch0')
        self.assertIsNone(self.m.destination)

    async def test_voice_switch_tells_the_app_and_hides_urls(self):
        self.register()
        self.m.on_destination = Mock()
        data = json.loads(await choose_minutes_destination(self.context, ' 家 族 '))
        self.assertEqual((data['status'], data['destination']), ('switched', '家族'))
        self.m.on_destination.assert_called_once_with('家族')
        self.assertNotIn('webhooks', json.dumps(data) + json.dumps(self.m.status()) + self.m.context())
        with patch('minutes.post_discord') as post:
            await self.meeting()
        self.assertEqual(post.call_args.args[0], HOME)

    async def test_voice_switch_to_an_unknown_name_keeps_the_current_one(self):
        data = json.loads(await choose_minutes_destination(self.context, '仕事'))
        self.assertEqual(data['status'], 'none_registered')
        self.register()
        self.m.on_destination = Mock()
        data = json.loads(await choose_minutes_destination(self.context, '学校'))
        self.assertEqual((data['status'], data['destination'], data['destinations']), ('not_found', '仕事', ['仕事', '家族']))
        self.m.on_destination.assert_not_called()
        data = json.loads(await choose_minutes_destination(self.context))
        self.assertEqual((data['status'], data['destination']), ('ok', '仕事'))


if __name__ == '__main__':
    unittest.main()
