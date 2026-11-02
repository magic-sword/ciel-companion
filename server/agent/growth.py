# -*- coding: utf-8 -*-
"""出来事から育つシエルの好み。会話の終わりに、本当にあった出来事（diary.py）を見て、好みを 1 つ足す・変える・外すかを決める。

人物像を 3 つに分けて持つ（参考：docs/ciel-growth-research-ja.md）：
- 芯：変わらない好み・苦手・こだわり（config/prompts/ciel_self.md）。ここでは変えない
- 育った好み：出来事から少しずつ育つもの（DB の ciel_likes。ここで書く）
- 物語：本当にあった出来事（DB の ciel_events。diary.py が書く）
研究で報告されている落とし穴を、モデル任せにせず、ここで止める：
- 1 回の出来事で好みを決めない：足す・書き直すには、根拠の出来事が MIN_EVIDENCE 個以上、しかも MIN_DAYS 日以上にまたがること
- 急に変わらない：1 回の会話で変えるのは 1 つまで、前に変えてから MIN_INTERVAL たってから。新しい出来事が無い会話では見直さない
- 増えすぎない：育った好みは MAX_LIKES 個まで
- いい方向だけに育てない：好き（like）のほかに、ちょっと苦手（dislike）・気になっている（curious）も育つ（指示文で頼む）
- あとから見直せる：根拠の出来事を写して持ち（出来事は古いものから消えるため）、変えた記録を ciel_like_history に残す。
  一覧・取り消しは self_admin.py
指示は config/prompts/ciel_growth.md。会話への渡し方は context()（会話モデルと内なる考えの両方に、芯のあとに足す）。
ログには好みの中身を出さない（何をしたかと数だけ）。中身はデバッグ用の会話ログにだけ残す。
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import openai

import debug_log
import models
from jst import JST

log = logging.getLogger('ciel-agent.growth')

MODEL = os.environ.get('CIEL_NOTES_MODEL', 'gpt-5.4-mini')   # メモ・関係の記録係と同じ文字のモデル
KINDS = {'like': '好きになってきた', 'dislike': 'ちょっと苦手になってきた', 'curious': 'まだよく分からないけれど気になっている'}
MAX_LIKES = 12
MIN_EVIDENCE = 2
MIN_DAYS = 2
MIN_INTERVAL = timedelta(hours=20)
EVENTS = 40          # 見せる出来事の数（新しい順）
TEXT_CHARS = 40
WHY_CHARS = 80
TIMEOUT = 30.0


def context(likes) -> str:
    """会話モデル・内なる考えに渡す形。育った好みが無ければ空"""
    if not likes:
        return ''
    lines = [f'- {KINDS.get(kind, kind)}：{text}' + (f'（{why}）' if why else '') for _, kind, text, why, _ in likes]
    return ('出来事から育ってきた好み（芯と同じように、自分の好みとして話してよい。きっかけを話すときは、本当にあったこととして'
            '気持ちと一緒に話す）：\n' + '\n'.join(lines))


def check(change, likes, events) -> str | None:
    """モデルが決めた変化を、決まりに照らす。通れば None、通らなければ理由"""
    action = change.get('action')
    if action not in ('add', 'update', 'remove'):
        return 'action'
    ids = {e[0] for e in events}
    evidence = change.get('evidence') if isinstance(change.get('evidence'), list) else []
    if any(not isinstance(i, int) or i not in ids for i in evidence):
        return 'unknown_evidence'
    days = {e[1].astimezone(JST).date() for e in events if e[0] in evidence}
    if action in ('add', 'update'):
        if change.get('kind') not in KINDS:
            return 'kind'
        text = change.get('text')
        if not isinstance(text, str) or not text.strip():
            return 'text'
        if len(set(evidence)) < MIN_EVIDENCE or len(days) < MIN_DAYS:
            return 'too_little_evidence'
        if any(text.strip() == t for _, _, t, _, _ in likes):
            return 'duplicate'
    if action == 'add' and len(likes) >= MAX_LIKES:
        return 'too_many'
    if action in ('update', 'remove'):
        if change.get('id') not in {like[0] for like in likes}:
            return 'unknown_like'
        if not evidence:
            return 'too_little_evidence'
    return None


class Grower:
    def __init__(self, store, diary, core: str, instructions: str, client=None) -> None:
        self.store = store      # speaker_store.Store（無ければ育てない）
        self.diary = diary      # diary.Diary（この会話で新しい出来事があったか）
        self.core = core        # config/prompts/ciel_self.md
        self.instructions = instructions
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    async def flush(self, now: datetime | None = None) -> str:
        """会話の終わりに 1 回。何をしたかを返す（テストとログのため）"""
        if self.store is None or self.diary is None or self.diary.added == 0:
            return 'skip'
        now = now or datetime.now(timezone.utc)
        last = await self.store.last_like_change()
        if last is not None and now - last < MIN_INTERVAL:
            return 'too_soon'
        likes = await self.store.ciel_likes()
        events = await self.store.ciel_events(EVENTS)
        if len(events) < MIN_EVIDENCE:
            return 'skip'
        request = {
            'core': self.core,
            'likes': [{'id': i, 'kind': k, 'text': t, 'why': w} for i, k, t, w, _ in likes],
            'events': [{'id': i, 'date': f'{at.astimezone(JST):%Y-%m-%d}', 'text': text} for i, at, _, text in events],
        }
        try:
            r = await self.client.chat.completions.create(
                model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=TIMEOUT,
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            models.record('growth', MODEL, getattr(r, 'usage', None))
            change = json.loads(r.choices[0].message.content or '{}').get('change') or {}
        except Exception as e:   # 育てられなくても、会話の後片付けは続ける
            log.warning('好みを見直せない: %s', type(e).__name__)
            return 'failed'
        if not isinstance(change, dict) or change.get('action') in (None, 'none'):
            log.info('好みは変えない（育った好み %d 個）', len(likes))
            return 'none'
        problem = check(change, likes, events)
        debug_log.record('growth', change=change, rejected=problem)
        if problem is not None:
            log.info('好みの変化を見送った（%s）', problem)
            return f'rejected:{problem}'
        action = change['action']
        old = next((like for like in likes if like[0] == change.get('id')), None)
        kind = change.get('kind') if action != 'remove' else old[1]
        text = change['text'].strip()[:TEXT_CHARS] if action != 'remove' else old[2]
        why = (change.get('why') or '').strip()[:WHY_CHARS] if action != 'remove' else old[3]
        evidence = [{'id': i, 'date': f'{at.astimezone(JST):%Y-%m-%d}', 'text': t}
                    for i, at, _, t in events if i in change['evidence']]
        await self.store.change_ciel_like(action, change.get('id'), kind, text, why, evidence)
        log.info('好みが育った（%s・%s、根拠の出来事 %d 個）', action, kind, len(evidence))
        return action
