import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import irodori_tts


class TTSRequestTests(unittest.IsolatedAsyncioTestCase):
    def response(self):
        response = MagicMock()
        response.read = AsyncMock(return_value=b'pcm')
        response.headers = {'X-Sample-Rate': '48000', 'X-Queue-Ms': '10'}
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        return response, context

    async def test_success_sends_session_and_request_ids_without_cancelling(self):
        _, context = self.response()
        http = MagicMock()
        http.post.return_value = context
        with patch.object(irodori_tts.aiohttp, 'ClientSession') as control:
            self.assertEqual(await irodori_tts.request_audio(http, {'text': 'synthetic'}, session_id='room-A'),
                             (b'pcm', 48000))
        sent = http.post.call_args.kwargs['json']
        self.assertEqual(sent['session_id'], 'room-A')
        self.assertEqual(len(sent['request_id']), 32)
        control.assert_not_called()

    async def test_interruption_cancels_the_same_request_on_server(self):
        response, context = self.response()
        entered, hold = asyncio.Event(), asyncio.Event()

        async def read():
            entered.set()
            await hold.wait()

        response.read.side_effect = read
        http = MagicMock()
        http.post.return_value = context
        control = MagicMock()
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=control)
        client_context.__aexit__ = AsyncMock(return_value=False)
        _, cancel_context = self.response()
        control.delete.return_value = cancel_context
        with patch.object(irodori_tts.aiohttp, 'ClientSession', return_value=client_context):
            task = asyncio.create_task(irodori_tts.request_audio(http, {'text': 'synthetic'}, session_id='room-B'))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        sent = http.post.call_args.kwargs['json']
        self.assertEqual(control.delete.call_args.args[0], irodori_tts.URL + '/' + sent['request_id'])
        self.assertEqual(control.delete.call_args.kwargs['params'], {'session_id': 'room-B'})
