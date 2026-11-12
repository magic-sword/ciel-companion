"""Session-scoped input validation, bounded reaction queue and speech lifecycle."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import inspect
import json
import logging
import math
import time
import uuid

import debug_log


log = logging.getLogger('ciel-agent.reactions')

POLICY = {  # trusted source -> kind -> (priority, maximum lifetime)
    'touch': {'touch.pull': (90, 5), 'touch.contact': (30, 5)},
    'game': {'game.damage': (90, 5), 'game.notice': (40, 30)},
    'work': {'work.result': (50, 30)},
    'comment': {'comment.received': (10, 30)},
    'song': {'song.change': (10, 3)},
    'minutes': {'minutes.notice': (50, 30)},
    'research': {'research.result': (50, 30)},
    'image': {'image.received': (30, 30)},
}


@dataclass
class Reaction:
    key: tuple
    kind: str
    priority: int
    deadline: float | None
    why: str
    kwargs: dict
    ready_at: float
    status: str = 'queued'
    handle: object = None
    result: asyncio.Future | None = None
    output_seen: bool = False
    quiet_seconds: float = 0.

    @property
    def conversation(self):
        return self.key[0] in ('game', 'work')

    def expired(self, now):
        return self.deadline is not None and now >= self.deadline


class Reactions:
    LIMIT = 64
    REMEMBER = 512
    POLL = .05

    def __init__(self, mouth, *, clock=time.monotonic, wall=time.time):
        self.mouth, self.clock, self.wall = mouth, clock, wall
        self.epochs = {s: uuid.uuid4().hex for s in POLICY}
        self.sequences = {s: 0 for s in POLICY}
        self.last_seq = {s: -1 for s in POLICY}
        self.seen = OrderedDict()
        self.queue = OrderedDict()
        self.speeches = OrderedDict()
        self.attachments = OrderedDict()
        self.active = None
        self.closed = False
        self.task = None
        self.publish = None
        self.singing = lambda: False
        self.emergency = None
        self.lease_until, self.lease_priority = 0., 0
        self.free_since = None

    def trace(self, event, stage):
        debug_log.record('reaction', event_id=event.key[-1], source=event.key[0], event_kind=event.kind,
                         stage=stage, at=round(self.clock(), 4))

    def envelope(self, source, kind, payload, *, event_id=None, epoch=None):
        self.sequences[source] += 1
        return {'v': 1, 'event_id': event_id or uuid.uuid4().hex,
                'source_epoch': epoch or self.epochs[source], 'seq': self.sequences[source],
                'kind': kind, 'occurred_at': self.wall(),
                'ttl_ms': int(POLICY[source][kind][1] * 1000), 'payload': payload}

    def reset(self, source):
        self.epochs[source] = uuid.uuid4().hex
        self.last_seq[source] = -1
        for entries in self.attachments.values():
            for event in entries:
                if event.key[0] == source and event.status == 'attached':
                    self.finish(event, 'disconnected')
        for entry in list(self.queue.values()):
            if entry.key[0] == source:
                self.finish(entry, 'disconnected')
        if self.active and self.active.key[0] == source:
            self.finish(self.active, 'disconnected')
            self.interrupt(self.active)

    def receive(self, source, envelope, *, why, kwargs=None, settle=0., expression=None, local_expression=False):
        """source/why/kwargs are host adapter arguments, never fields trusted from a sender."""
        if self.closed or not isinstance(source, str) or source not in POLICY or not isinstance(envelope, dict):
            return self.reject('input', 'closed_or_invalid_source')
        kind = envelope.get('kind')
        if type(envelope.get('v')) is not int or envelope.get('v') != 1 or not isinstance(kind, str) or kind not in POLICY[source]:
            return self.reject(source, 'unsupported_contract')
        epoch, seq, identifier = envelope.get('source_epoch'), envelope.get('seq'), envelope.get('event_id')
        if epoch != self.epochs[source] or type(seq) is not int or not isinstance(identifier, str) or not 1 <= len(identifier) <= 160:
            return self.reject(source, 'invalid_identity_or_epoch')
        key = (source, epoch, identifier)
        if key in self.seen or seq <= self.last_seq[source]:
            return self.reject(source, 'duplicate_or_old_sequence')
        ttl, at = envelope.get('ttl_ms'), envelope.get('occurred_at')
        if type(ttl) not in (int, float) or type(at) not in (int, float) or not math.isfinite(ttl) or not math.isfinite(at):
            return self.reject(source, 'invalid_time')
        try:
            size = len(json.dumps(envelope.get('payload'), ensure_ascii=False, allow_nan=False))
            request_size = len(json.dumps(kwargs or {}, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError):
            return self.reject(source, 'invalid_payload')
        if not isinstance(envelope.get('payload'), dict) or size > 8192 or request_size > 16000 or at > self.wall() + 1 or ttl <= 0:
            return self.reject(source, 'oversized_or_invalid_payload')
        priority, maximum = POLICY[source][kind]
        remaining = min(ttl / 1000, maximum) - max(0, self.wall() - at)
        if remaining <= 0:
            return self.reject(source, 'expired')
        now = self.clock()
        event = Reaction(key, kind, priority, now + remaining, why, dict(kwargs or {}), now + max(0, settle))
        if event.conversation:
            # Freshness is checked at ingestion. Accepted facts wake ordinary conversation.
            event.deadline = None
        event.quiet_seconds = max(0, settle)
        self.last_seq[source] = seq
        self.seen[key] = event
        while len(self.seen) > self.REMEMBER:
            self.seen.popitem(last=False)
        self.trace(event, 'received')
        if source in ('game', 'work'):
            history = getattr(getattr(self.mouth.session, 'userdata', None), 'history', None)
            if history is None:
                from conversation import Conversation
                history = self.mouth.session.userdata.history = Conversation()
            history.event(source=source, event_id=f'{epoch}:{identifier}', occurred_at=at,
                          kind=kind, fact=envelope['payload'].get('fact', ''))
            # Facts are durable conversation events; generation is only a wake-up.
            event.kwargs.pop('instructions', None)
        if expression:
            if local_expression:
                if now >= self.lease_until or priority >= self.lease_priority:
                    self.lease_priority, self.lease_until = priority, now + min(3, remaining)
                self.trace(event, 'expression_local')
            else:
                self.expression(expression, priority=priority, seconds=min(3, remaining), event=event)
        if kind == 'song.change':
            event.status = 'visual_only'
            return event
        # Coalesce only within the same trusted source and kind. Do not combine authorities.
        for old in list(self.queue.values()):
            if old.key[0] == source and old.kind == kind:
                self.finish(old, 'superseded')
        if len(self.queue) >= self.LIMIT:
            victim = min(self.queue.values(), key=lambda e: (e.priority, e.ready_at))
            if victim.priority > priority:
                event.status = 'overflow'
                self.trace(event, 'overflow')
                return event
            self.finish(victim, 'overflow')
        self.queue[key] = event
        if self.active and not self.active.conversation and priority > self.active.priority:
            self.finish(self.active, 'preempted')
            self.interrupt(self.active)
        self.start()
        return event

    def reject(self, source, reason):
        debug_log.record('reaction_rejected', source=source, reason=reason)
        report = log.debug if reason in ('expired', 'duplicate_or_old_sequence', 'closed_or_invalid_source') else log.warning
        report('サービス入力を拒否 source=%s reason=%s', source, reason)
        return None

    def submit(self, source, kind, payload, **options):
        event_id = options.pop('event_id', None)
        return self.receive(source, self.envelope(source, kind, payload, event_id=event_id), **options)

    def expression(self, name, *, priority=0, seconds=3, event=None):
        if not math.isfinite(seconds):
            return False
        seconds = min(10, seconds if seconds > 0 else 3)
        now = self.clock()
        if self.closed or (now < self.lease_until and priority < self.lease_priority):
            return False
        if now < self.lease_until and priority > 0 and priority == self.lease_priority and event is None:
            return False
        self.lease_priority, self.lease_until = priority, now + seconds
        if self.publish:
            self.publish({'v': 2, 'type': 'character.expression', 'expression': name, 'intensity': 1.,
                          'ttl_ms': int(seconds * 1000), 'expires_unix_ms': int((self.wall() + seconds) * 1000), 'priority': priority,
                          'event_id': event.key[-1] if event else ''})
        if event:
            self.trace(event, 'expression_requested')
        return True

    def finish(self, event, status):
        self.queue.pop(event.key, None)
        event.status = status
        if event.result and not event.result.done():
            event.result.set_result(event.handle if status == 'spoken' else None)
        self.trace(event, status)

    def interrupt(self, event):
        handle = event.handle
        if handle and hasattr(handle, 'interrupt'):
            handle.interrupt(force=True)

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())

    def allowed(self, speech_id):
        event = self.speeches.get(speech_id)
        return event is None or (not self.closed and event.status == 'generating' and
                                 not getattr(event.handle, 'interrupted', False) and not event.expired(self.clock()))

    def current(self):
        return self.speeches.get(getattr(getattr(self.mouth.session, 'current_speech', None), 'id', None))

    def take(self, source):
        for event in list(self.queue.values()):
            if event.expired(self.clock()):
                self.finish(event, 'expired')
            elif event.key[0] == source:
                self.queue.pop(event.key, None)
                event.status = 'attached'
                speech = getattr(self.mouth.session, 'current_speech', None)
                if getattr(speech, 'id', None):
                    self.attachments.setdefault(speech.id, []).append(event)
                    while len(self.attachments) > self.REMEMBER:
                        self.attachments.popitem(last=False)
                return event
        return None

    def on_said(self, notice):
        if self.closed:
            return
        item = notice.item
        if getattr(item, 'role', None) != 'assistant':
            return
        speech = getattr(self.mouth.session, 'current_speech', None)
        active = self.speeches.get(getattr(speech, 'id', None))
        if active and active.status == 'generating':
            text = (getattr(item, 'text_content', '') or '').strip()
            active.output_seen = bool(text and text != '[silent]' and not getattr(item, 'interrupted', False))
        for event in self.attachments.pop(getattr(speech, 'id', None), []):
            if event.status == 'attached':
                self.finish(event, 'cancelled' if getattr(item, 'interrupted', False) or
                            not (getattr(item, 'text_content', '') or '').strip() else 'spoken')

    async def wait(self, event):
        if event is None or event.status != 'queued':
            return None
        event.result = asyncio.get_running_loop().create_future()
        try:
            return await event.result
        except asyncio.CancelledError:
            self.finish(event, 'cancelled')
            self.interrupt(event)
            raise

    async def run(self):
        try:
            while not self.closed and (self.queue or self.active):
                now = self.clock()
                for event in list(self.queue.values()):
                    if event.expired(now):
                        self.finish(event, 'expired')
                blocked = self.mouth.busy() or self.singing()
                if blocked:
                    self.free_since = None
                elif self.free_since is None:
                    self.free_since = now
                ready = [e for e in self.queue.values() if e.ready_at <= now and not blocked and
                         now - self.free_since >= e.quiet_seconds]
                if not ready:
                    await asyncio.sleep(self.POLL)
                    continue
                event = max(ready, key=lambda e: (e.priority, -e.ready_at))
                self.queue.pop(event.key, None)
                self.active = event
                event.status = 'generating'
                self.trace(event, 'generation_started')
                playout = None
                try:
                    handle = event.handle = self.mouth.say(event.why, **event.kwargs)
                    speech_id = getattr(handle, 'id', None)
                    if speech_id:
                        self.speeches[speech_id] = event
                        while len(self.speeches) > self.REMEMBER:
                            self.speeches.popitem(last=False)
                    if inspect.isawaitable(handle):
                        playout = asyncio.ensure_future(handle)
                        if event.conversation:
                            await asyncio.shield(playout)
                        else:
                            await asyncio.wait_for(asyncio.shield(playout), max(.001, event.deadline - self.clock()))
                    if event.status == 'generating':
                        self.finish(event, 'cancelled' if getattr(handle, 'interrupted', False) else
                                    'spoken' if event.output_seen else 'unconfirmed')
                except TimeoutError:
                    self.finish(event, 'expired')
                    self.interrupt(event)
                except asyncio.CancelledError:
                    self.finish(event, 'cancelled')
                    self.interrupt(event)
                    raise
                except Exception:
                    self.finish(event, 'failed')
                finally:
                    if playout and not playout.done():
                        playout.cancel()
                        await asyncio.gather(playout, return_exceptions=True)
                    self.active = None
                    self.free_since = None
        finally:
            self.task = None

    async def close(self):
        self.closed = True
        for entries in self.attachments.values():
            for event in entries:
                self.finish(event, 'closed')
        self.attachments.clear()
        for event in list(self.queue.values()):
            self.finish(event, 'closed')
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
