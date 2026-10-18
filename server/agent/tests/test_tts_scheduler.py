import importlib.util
from pathlib import Path
import sys
import threading
import unittest


spec = importlib.util.spec_from_file_location('ciel_tts_scheduler', Path(__file__).resolve().parents[2] / 'tts-irodori' / 'scheduler.py')
scheduler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scheduler
spec.loader.exec_module(scheduler)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = scheduler.FairScheduler()
        self.started, self.release = threading.Event(), threading.Event()
        self.order = []

        def first():
            self.started.set()
            self.release.wait(3)
            self.order.append('first')

        self.first = self.scheduler.submit('A', 'first', first)
        self.assertTrue(self.started.wait(3))

    def tearDown(self):
        self.release.set()
        self.scheduler.close()

    def submit(self, room, request, **kwargs):
        return self.scheduler.submit(room, request, lambda: self.order.append(request), **kwargs)

    def test_rooms_take_turns_instead_of_draining_one_rooms_backlog(self):
        futures = [self.submit('A', 'a1'), self.submit('A', 'a2'), self.submit('B', 'b1'), self.submit('B', 'b2')]
        self.release.set()
        for future in futures:
            future.result(3)
        self.assertEqual(self.order, ['first', 'a1', 'b1', 'a2', 'b2'])

    def test_cancel_queued_request_prevents_gpu_work_and_checks_owner(self):
        future = self.submit('B', 'cancel')
        self.assertFalse(self.scheduler.cancel('C', 'cancel'))
        self.assertTrue(self.scheduler.cancel('B', 'cancel'))
        self.assertTrue(future.cancelled())
        self.release.set()
        self.first.result(3)
        self.assertNotIn('cancel', self.order)

    def test_expired_request_never_runs(self):
        future = self.submit('B', 'expired', timeout=0)
        self.release.set()
        with self.assertRaises(TimeoutError):
            future.result(3)
        self.assertNotIn('expired', self.order)

    def test_room_capacity_cannot_block_other_rooms(self):
        for i in range(3):
            self.submit('A', str(i))
        with self.assertRaises(scheduler.QueueFull):
            self.submit('A', 'overflow')
        self.submit('B', 'allowed')

    def test_running_cancel_discards_result_without_interrupting_gpu_call(self):
        self.assertTrue(self.scheduler.cancel('A', 'first'))
        self.release.set()
        self.scheduler.close()
        self.assertTrue(self.first.cancelled())
        self.assertEqual(self.order, ['first'])
