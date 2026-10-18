# -*- coding: utf-8 -*-
"""シエルがその人をどう思っているか（関係）を、会話の終わりに書き直す（会話を止めない）。

- 持つもの（speaker_store.Relationship、1 人 1 行）：親しさの段階（STAGES）、シエルの気持ち（一人称の短い文）、
  次の会話まで続く一時的な気分（ちょっと拗ねている、など）。
- 書くのは会話が終わるとき 1 回だけ。その会話の共通履歴（conversation.Conversation）と、今の関係・メモを
  文字のモデル（CIEL_NOTES_MODEL）に渡して書き直してもらう。指示は config/prompts/relationship.md。
- 段階は下げない。上げるのは 1 回の会話で 1 つまで、しかも今の段階で何回か（STAGE_UP_SESSIONS）ちゃんと話してから。
  ちょっとした会話で急に親しくなったり冷めたりしないように、上げてよいかはここで決め、モデルには「上げるか」だけ聞く。
- 対象は、声を覚えていて、お話を覚えることにも同意した人だけ（メモと同じ同意の範囲）。人を消すと関係も消える。
- 会話への渡し方は context()（speakers.py が、本人だと分かった最初の発言に添える）。
- ログには、気持ちの中身も会話も出さない（段階の番号だけ）。
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import openai

from speaker_store import Relationship

log = logging.getLogger('ciel-agent.relationship')

MODEL = os.environ.get('CIEL_NOTES_MODEL', 'gpt-5.4-mini')   # メモの記録係と同じ文字のモデル

STAGES = ['はじめまして', '顔なじみ', '仲良し', '大切な人']
STAGE_UP_SESSIONS = [2, 4, 8]   # 次の段階に上がるには、今の段階でちゃんと話した会話がこの数以上（この会話も数える）
FIRST_MAX_STAGE = 2             # 初めて関係を書くとき（前からメモがある人）、メモから決めてよい段階の上限
MIN_TURNS = 4                   # 1 回の会話で、その人がこの回数以上話したら「ちゃんと話した」会話として数える
CONTEXT_LINES = 80              # 渡す会話の行数（最後から）
LONELY_DAYS = 7                 # 顔なじみ以上の人と、この日数以上会っていなければ、少し寂しかったことにする
MAX_FEELING_CHARS = 200
MAX_MOOD_CHARS = 80


def context(name: str, r: Relationship | None, last_seen: datetime | None, private: bool) -> str:
    """会話モデルに渡す 1 行。private（ひとり・身近な人）でなければ、口調のための段階だけ"""
    if r is None:
        return ''
    stage = STAGES[min(max(r.stage, 0), len(STAGES) - 1)]
    if not private:
        return f'\n[{name}さんとの親しさ：{stage}（口調だけに表す。口に出さない）]'
    # 会えたときに表に出やすい順（寂しさ・気分を先に。気持ちは前の会話までの思いで、下敷きにするもの）
    parts = [stage]
    if r.stage >= 1 and last_seen is not None and datetime.now(timezone.utc) - last_seen >= timedelta(days=LONELY_DAYS):
        parts.append('しばらく会えなくて、少し寂しかった')
    if r.mood:
        parts.append(f'前の会話から続いている気分：{r.mood.rstrip("。")}')
    if r.feeling:
        parts.append(f'前の会話までの気持ち：{r.feeling.rstrip("。")}')
    return f'\n[{name}さんとの関係（シエルの心の中。そのまま口に出さない）：' + '。'.join(parts) + ']'


class RelationKeeper:
    def __init__(self, book, note_taker, instructions: str, history) -> None:
        self.book = book               # speakers.SpeakerBook
        self.note_taker = note_taker   # notes.NoteTaker（本人からの「忘れて」の依頼）
        self.history = history
        self.instructions = instructions
        self._client = openai.AsyncOpenAI()

    async def flush(self) -> None:
        """会話が終わるとき：この会話で話した、同意している人ごとに関係を書き直す"""
        turns: dict[int, int] = {}
        for o, _, _ in self.history.personal_lines():
            if o is not None and o.person_id is not None:
                turns[o.person_id] = turns.get(o.person_id, 0) + 1
        for pid in self.note_taker.forgotten:   # 忘れてと頼まれた人は、話した回数が少なくても書き直す
            turns.setdefault(pid, 0)
        for pid, n in turns.items():
            try:
                await self._update(pid, n)
            except Exception as e:   # 書けなくても、次の会話で書き直せばよい
                log.warning('関係 #%d を書けない：%s', pid, type(e).__name__)

    async def _update(self, pid: int, n_turns: int) -> None:
        for _ in range(3):
            if await self._update_once(pid, n_turns) is not False:
                return
        log.info('関係 #%d：同時更新のため今回は保存を見送る', pid)

    async def _update_once(self, pid: int, n_turns: int) -> bool | None:
        store = self.book.store
        k = next((k for k in self.book.known if k.person_id == pid), None)
        if store is None or k is None or not k.notes_ok or (n_turns < 2 and pid not in self.note_taker.forgotten):
            return
        snapshot = await store.memory_snapshot(pid)
        if snapshot is None or not snapshot['consent'] or snapshot['blocked']:
            return
        current = snapshot['relationship']
        first = current is None
        r = current or Relationship()
        if n_turns >= MIN_TURNS:
            r.sessions += 1
            r.stage_sessions += 1
        can_up = not first and r.stage < len(STAGES) - 1 and r.stage_sessions >= STAGE_UP_SESSIONS[r.stage]
        lines = self.history.personal_lines()[-CONTEXT_LINES:]
        request = {
            'today': datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d（%a）'),
            'person': snapshot['name'],
            'first': first,
            'stages': [f'{i}：{s}' for i, s in enumerate(STAGES)],
            'current': None if first else {'stage': r.stage, 'feeling': r.feeling, 'mood': r.mood},
            'can_stage_up': can_up,
            'notes': [t for _, t in snapshot['notes']],
            'forget_requests': list(dict.fromkeys([*self.note_taker.forgotten.get(pid, []),
                                                   *(f['request'] for f in snapshot['forgets'])])),
            'days_since_last_talk': (datetime.now(timezone.utc) - k.last_seen).days if k.last_seen else None,
            'conversation': [{'speaker': who, 'is_person': o is not None and o.person_id == pid, 'text': text}
                             for o, who, text in lines],
        }
        r_ = await self._client.chat.completions.create(
            model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'},
            messages=[{'role': 'system', 'content': self.instructions},
                      {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
        result = json.loads(r_.choices[0].message.content or '{}')
        before = r.stage
        if first:
            stage = result.get('stage')
            r.stage = min(max(stage, 0), FIRST_MAX_STAGE) if isinstance(stage, int) else 0
            r.stage_sessions = 0
        elif can_up and result.get('stage_up') is True:
            r.stage += 1
            r.stage_sessions = 0
        feeling, mood = result.get('feeling'), result.get('mood')
        if isinstance(feeling, str) and feeling.strip():
            r.feeling = feeling.strip()[:MAX_FEELING_CHARS]
        if isinstance(mood, str):
            r.mood = mood.strip()[:MAX_MOOD_CHARS]
        if not await store.apply_relationship(pid, snapshot, r):
            return False
        log.info('関係 #%d：段階 %d → %d（ちゃんと話した会話 %d、この段階で %d）%s', pid, before, r.stage,
                 r.sessions, r.stage_sessions, '、初めて書いた' if first else '')
