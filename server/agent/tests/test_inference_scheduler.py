import asyncio
import unittest

from inference_scheduler import InferenceScheduler


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def hold(self, scheduler, name, order, gate, priority='decision'):
        async with scheduler.slot(priority) as queued:
            order.append((name, queued >= 0))
            await gate.wait()

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0)

    async def test_slots_limit_concurrency_and_waiters_run_by_priority_then_arrival(self):
        scheduler, gate, order = InferenceScheduler(2), asyncio.Event(), []
        tasks = [asyncio.create_task(self.hold(scheduler, n, order, gate, p)) for n, p in
                 [('a', 'decision'), ('b', 'decision'), ('summary', 'background'), ('turn1', 'decision'), ('turn2', 'decision')]]
        await self.settle()
        self.assertEqual([n for n, _ in order], ['a', 'b'])
        self.assertEqual(scheduler.status(), {'slots': 2, 'active': 2, 'waiting': 3})
        gate.set()
        await asyncio.gather(*tasks)
        self.assertEqual([n for n, _ in order], ['a', 'b', 'turn1', 'turn2', 'summary'])
        self.assertEqual(scheduler.status(), {'slots': 2, 'active': 0, 'waiting': 0})

    async def test_cancellation_while_waiting_or_running_never_leaks_a_slot(self):
        scheduler, gate, order = InferenceScheduler(1), asyncio.Event(), []
        running = asyncio.create_task(self.hold(scheduler, 'running', order, gate))
        await self.settle()
        waiting = asyncio.create_task(self.hold(scheduler, 'waiting', order, gate))
        await self.settle()
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)
        self.assertEqual(scheduler.status()['waiting'], 0)
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        self.assertEqual(scheduler.status()['active'], 0)
        later = asyncio.create_task(self.hold(scheduler, 'later', order, gate))
        await self.settle()
        gate.set()
        await later
        self.assertEqual([n for n, _ in order], ['running', 'later'])

    async def test_waiter_cancelled_as_it_is_granted_passes_the_slot_on(self):
        scheduler, gate, order = InferenceScheduler(1), asyncio.Event(), []
        scheduler.active = 1  # A request outside this test holds the only slot.
        second = asyncio.create_task(self.hold(scheduler, 'second', order, gate))
        third = asyncio.create_task(self.hold(scheduler, 'third', order, gate))
        await self.settle()
        scheduler._release()  # The holder finishes and grants "second" ...
        second.cancel()       # ... which is cancelled before it can resume.
        gate.set()
        await asyncio.gather(second, third, return_exceptions=True)
        self.assertEqual([n for n, _ in order], ['third'])
        self.assertEqual(scheduler.status(), {'slots': 1, 'active': 0, 'waiting': 0})

    def test_invalid_configuration_is_rejected(self):
        for slots in (0, -1, 1.5, '2'):
            with self.assertRaises(ValueError):
                InferenceScheduler(slots)


if __name__ == '__main__':
    unittest.main()
