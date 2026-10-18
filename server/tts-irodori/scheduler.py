"""Bounded round-robin scheduling for a single GPU. Contains no model or audio data."""
import collections
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field


class QueueFull(RuntimeError):
    pass


@dataclass
class Job:
    session: str
    request: str
    run: object
    deadline: float
    queued: float = field(default_factory=time.monotonic)
    future: Future = field(default_factory=Future)


class FairScheduler:
    def __init__(self, *, per_session=4, capacity=64):
        self.per_session, self.capacity = per_session, capacity
        self._lock = threading.Lock()
        self._queues = {}
        self._order = collections.deque()
        self._jobs = {}
        self._running = False
        self._worker = ThreadPoolExecutor(max_workers=1)

    def submit(self, session, request, run, *, timeout=25):
        with self._lock:
            key = (session, request)
            if key in self._jobs:
                raise ValueError('duplicate request')
            if len(self._jobs) >= self.capacity or sum(k[0] == session for k in self._jobs) >= self.per_session:
                raise QueueFull('synthesis queue is full')
            job = Job(session, request, run, time.monotonic() + timeout)
            self._jobs[key] = job
            if session not in self._queues:
                self._queues[session] = collections.deque()
                self._order.append(session)
            self._queues[session].append(job)
            if not self._running:
                self._running = True
                self._worker.submit(self._drain)
            return job.future

    def cancel(self, session, request):
        with self._lock:
            job = self._jobs.get((session, request))
            if job is None:
                return False
            job.future.cancel()
            queue = self._queues.get(session)
            if queue is not None and job in queue:
                queue.remove(job)
                self._jobs.pop((session, request), None)
                if not queue:
                    del self._queues[session]
                    self._order.remove(session)
            return True

    def _drain(self):
        while True:
            with self._lock:
                if not self._order:
                    self._running = False
                    return
                session = self._order.popleft()
                queue = self._queues[session]
                job = queue.popleft()
                if queue:
                    self._order.append(session)
                else:
                    del self._queues[session]
            started = time.monotonic()
            try:
                if started >= job.deadline:
                    raise TimeoutError('synthesis expired in queue')
                if not job.future.cancelled():
                    result = job.run()
                    with self._lock:
                        if not job.future.cancelled():
                            job.future.set_result((result, started - job.queued))
            except Exception as e:
                with self._lock:
                    if not job.future.cancelled():
                        job.future.set_exception(e)
            finally:
                with self._lock:
                    self._jobs.pop((job.session, job.request), None)

    def close(self):
        self._worker.shutdown(wait=True)
