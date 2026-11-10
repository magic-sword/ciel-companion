import asyncio
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace as Obj
from inference_activity import Activity, Deferred


class ActivityTest(unittest.IsolatedAsyncioTestCase):
    async def test_background_stream_collects_content_and_usage_then_closes(self):
        import models
        usage = Obj(prompt_tokens=10, completion_tokens=2)
        class Stream:
            close = AsyncMock()
            def __aiter__(self):
                async def chunks():
                    yield Obj(choices=[], usage=None)  # prefill progress
                    yield Obj(choices=[Obj(delta=Obj(content='{"ok":true}'))], usage=None)
                    yield Obj(choices=[], usage=usage)
                return chunks()
        stream = Stream()
        create = AsyncMock(return_value=stream)
        result = await models.background_completion(Obj(chat=Obj(completions=Obj(create=create))), model='local')
        self.assertEqual(result.choices[0].message.content, '{"ok":true}')
        self.assertIs(result.usage, usage)
        stream.close.assert_awaited_once()
        self.assertTrue(create.call_args.kwargs['stream'])

    async def test_busy_does_not_start_background_and_idle_can_resume(self):
        activity = Activity()
        operation = AsyncMock(return_value='saved')
        activity.update(user=True)
        with self.assertRaises(Deferred):
            await activity.run(operation)
        operation.assert_not_called()
        activity.update(user=False)
        activity.quiet_since -= 4
        self.assertEqual(await activity.run(operation), 'saved')

    async def test_foreground_cancels_only_inference_and_reports_retryable_deferral(self):
        activity = Activity()
        started, stopped = asyncio.Event(), asyncio.Event()
        async def operation():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        task = asyncio.create_task(activity.run(operation))
        await started.wait()
        activity.update(agent=True)
        with self.assertRaises(Deferred):
            await task
        self.assertTrue(stopped.is_set())
        self.assertFalse(activity.requests)

    async def test_shutdown_cancellation_is_not_swallowed(self):
        activity = Activity()
        task = asyncio.create_task(activity.run(AsyncMock(side_effect=lambda: None)))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
