# -*- coding: utf-8 -*-
"""シエルの口：シエルを話させる入り口は、ここ 1 つにする。

それまでは、返事（turns.py）・自分から話しかける（initiative.py）・議事録の知らせ（agent.py）・歌（singing.py）・
タッチ（touch.py）・声の登録（agent.py）・あいさつが、それぞれ session.generate_reply を呼び、今話してよいかも
それぞれが決めていた（11 か所。2026-10-30）。ここに集め、なぜ話すか（why）を記録する。
- say：今すぐ話させる（相手への返事・頼まれた一言）。
- say_when_free：だれも話しておらず、シエルも考え中・話している最中でない切れ目を待ってから話させる（会議の発言に
  かぶせない）。待ちきれなければ話さない（anyway=True なら、待ったあとで話す）。
- busy：今が切れ目でないか（だれかが話している・シエルが考え中・話している）。
ログ・デバッグ用の会話ログには、なぜ話したか（why）と、その回数だけを出す（中身は debug_log の reply_request）。
"""
import asyncio
import collections
import logging
import time

import debug_log
from reactions import Reactions

log = logging.getLogger('ciel-agent.mouth')

WHY = ('greeting', 'reply', 'initiative', 'minutes', 'song', 'touch', 'enrolled', 'research', 'comment',
       'game', 'image')   # comment：配信のコメントへの返事。game：ゲームの出来事・頼まれた技の結果（game_env.py）。
                          # image：見せてもらった画像を見る（eyes.py）
FREE_POLL = 0.25


class Mouth:
    def __init__(self, session) -> None:
        self.session = session
        self.reactions = Reactions(self)
        self.counts: collections.Counter[str] = collections.Counter()
        self.before_say = None   # 話させる直前に why を知らせる先（pipeline の心が、考える番の返事かを知る。mind.py）
        self._handed = collections.OrderedDict()   # 発話ごとに、文脈へ渡した通知IDを保持する

    def busy(self) -> bool:
        s = self.session
        return (getattr(s, 'user_state', None) == 'speaking'
                or getattr(s, 'agent_state', None) in ('thinking', 'speaking', 'initializing'))

    def say(self, why: str, **kwargs):
        """今すぐ話させる。generate_reply の返り（SpeechHandle）をそのまま返す"""
        self.counts[why] += 1
        log.info('口：%s', why)
        debug_log.record('speak', why=why)
        if self.before_say is not None:
            self.before_say(why)
        return self.session.generate_reply(**kwargs)

    async def say_when_free(self, why: str, *, wait: float = 30.0, anyway: bool = False, settle: float = 0.0,
                            **kwargs):
        """切れ目を wait 秒まで待ってから話させる。settle 秒は続けて切れ目であること（話の途中の息つぎで言い出さない）。
        待ちきれず anyway でなければ None（呼んだ側が別の機会に回す）"""
        if not await self._free(wait, settle) and not anyway:
            log.info('口：%s は切れ目が来ないので話さない', why)
            return None
        return self.say(why, **kwargs)

    async def _free(self, wait: float, settle: float) -> bool:
        """切れ目が settle 秒続くのを wait 秒まで待つ。来たら True"""
        deadline = time.monotonic() + wait
        free_since = None
        while time.monotonic() < deadline:
            if self.busy():
                free_since = None
            elif free_since is None:
                free_since = time.monotonic()
            if free_since is not None and time.monotonic() - free_since >= settle:
                return True
            await asyncio.sleep(FREE_POLL)
        return not self.busy()

    def say_latest(self, why: str, *, settle: float = 0., wait: float = 30., merge: bool = False, **kwargs):
        kinds = {'minutes': 'minutes.notice', 'research': 'research.result',
                 'image': 'image.received', 'game': 'game.notice'}
        if why not in kinds:
            raise ValueError('unknown notice source')
        kind = kinds[why]
        if merge and kwargs.get('instructions'):
            previous = next((event for event in self.reactions.queue.values()
                             if event.key[0] == why and event.kind == kind and
                             not event.expired(self.reactions.clock())), None)
            if previous:
                kwargs = {**kwargs, 'instructions': previous.kwargs.get('instructions', '') + '\n' + kwargs['instructions']}
        envelope = self.reactions.envelope(why, kind, {'fact': kwargs.get('instructions', '')})
        envelope['ttl_ms'] = min(30000, wait * 1000)
        return self.reactions.receive(why, envelope, why=why, kwargs=kwargs, settle=settle)

    def waiting(self) -> dict[str, str]:
        pending = [event for event in self.reactions.queue.values()
                   if not event.expired(self.reactions.clock()) and event.key[0] in ('minutes', 'research', 'image', 'game', 'work')]
        speech_id = getattr(getattr(self.session, 'current_speech', None), 'id', None)
        result = {}
        for event in pending:
            if event.key[0] in ('game', 'work') or event.kwargs.get('instructions'):
                result[event.why] = event.kwargs.get('instructions', '')
                self._handed[(speech_id, event.why)] = event.key
        while len(self._handed) > self.reactions.REMEMBER:
            self._handed.popitem(last=False)
        return result

    def drop(self, why: str) -> None:
        speech_id = getattr(getattr(self.session, 'current_speech', None), 'id', None)
        key = self._handed.pop((speech_id, why), None)
        event = self.reactions.queue.get(key)
        if event:
            self.reactions.finish(event, 'spoken_in_reply')

    def react_latest(self, why, *, instructions, settle=0., merge=False, reaction_kind=None, reaction_event=None):
        source = 'work' if reaction_kind == 'work.result' else 'game'
        kind = ('work.result' if source == 'work' else
                'game.died' if reaction_kind == 'died' else
                'game.damage' if reaction_kind in ('hurt', 'died', 'flee') else 'game.notice')
        payload = {'fact': instructions}
        if reaction_event and 'subject' in reaction_event:
            payload.update(subject=reaction_event['subject'], observation=reaction_event['observation'])
        envelope = self.reactions.envelope(source, kind, payload,
            event_id=reaction_event.get('event_id') if reaction_event else None)
        if reaction_event:
            envelope['occurred_at'] = reaction_event['occurred_at']
        event = self.reactions.receive(source, envelope, why=why,
            kwargs={'instructions': instructions}, settle=settle,
            expression='teary' if kind in ('game.damage', 'game.died') else None)
        if event is not None and reaction_kind == 'died' and self.reactions.emergency:
            self.reactions.emergency()
        return event

    async def react_comment(self, why, *, instructions, wait=30, settle=0., event_id=None,
                           occurred_at=None, **kwargs):
        envelope = self.reactions.envelope('comment', 'comment.received', {}, event_id=event_id)
        if occurred_at is not None:
            envelope['occurred_at'] = occurred_at
        envelope['ttl_ms'] = min(30000, wait * 1000)
        event = self.reactions.receive('comment', envelope, why='comment',
            kwargs={'instructions': instructions, **kwargs}, settle=settle)
        return await self.reactions.wait(event)

    def summary(self) -> None:
        """会話の終わりに、なぜ何回話したかを出す"""
        if self.counts:
            log.info('口：この会話で話した回数 %s', dict(self.counts))
            debug_log.record('speak_summary', counts=dict(self.counts))


def of(session) -> Mouth:
    """その会話の口（agent.py が session.userdata.mouth に置く）。無ければ（試験など）その場で作る"""
    mouth = getattr(getattr(session, 'userdata', None), 'mouth', None)
    if isinstance(mouth, Mouth):
        return mouth
    existing = getattr(session, '_ciel_mouth', None)
    if isinstance(existing, Mouth):
        return existing
    instance = Mouth(session)
    session._ciel_mouth = instance
    return instance
