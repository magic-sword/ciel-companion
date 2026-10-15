# -*- coding: utf-8 -*-
"""その人について覚えておくメモを、会話の裏で書く（会話モデルには書かせない）。

- 会話モデル（Realtime API）に道具で書かせると、そのたびに返事が遅れ、二重に話すこともあるので、
  書くのは別の文字のモデル（既定 gpt-5.4-mini、CIEL_NOTES_MODEL）に、会話の流れを止めずに任せる。
- 会話の文字起こし（LiveKit が Realtime API で作る）に、話者の判定（speakers.py）を添えてためておく。
  同意した人（声を覚えていて、お話を覚えることにも同意した人）が何回か話すか、しばらく話が途切れたら、
  その人のメモ（DB）と最近の会話を渡して、足す・書き直す・消すを決めてもらう。会話が終わるときにも書く。
- 何を覚えるか・覚えないかは config/prompts/notes.md。読むのは会話モデルが道具で（tools/memory.py）、本人が話しているときだけ。
- ログには、メモの中身も会話も出さない（件数だけ）。
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
import logging
import os

import openai

import emotion
import speakers

log = logging.getLogger('ciel-agent.notes')

MODEL = os.environ.get('CIEL_NOTES_MODEL', 'gpt-5.4-mini')
TURNS = 4            # 同意した人がこの回数話したら書く
IDLE_SECONDS = 40    # 同意した人が話してから、この秒数だれも話さなければ書く
CONTEXT_LINES = 30   # 1 回に渡す会話の行数（ほかの人の発言も、文脈として含める）
MAX_NOTE_CHARS = 120


class NoteTaker:
    def __init__(self, book: speakers.SpeakerBook, instructions: str) -> None:
        self.book = book
        self.instructions = instructions
        self.lines: list[tuple[int | None, str, str]] = []   # （同意した人の番号 または None、話者、文）
        self._done: dict[int, int] = {}                       # 人ごとに、どこまでメモにしたか（lines の位置）
        self._count: dict[int, int] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._timer: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._client = openai.AsyncOpenAI()

    def on_user_text(self, text: str) -> None:
        """相手の発言の文字起こし（確定したもの）。直前に判定した話者の発言とみなす"""
        if not text.strip():
            return
        k = self.book.current_person()
        sp = self.book.last
        label = (sp.name or sp.label) if sp else '不明'
        pid = k.person_id if k is not None and k.notes_ok else None
        self.lines.append((pid, label, text.strip()))
        if pid is None:
            return
        self._count[pid] = self._count.get(pid, 0) + 1
        if self._count[pid] >= TURNS:
            self._start(pid)
        else:
            self._arm_timer()

    def on_ciel_text(self, text: str) -> None:
        text = ciel_text(text)
        if text:
            self.lines.append((None, 'シエル', text))

    def _arm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.create_task(self._idle())

    async def _idle(self) -> None:
        await asyncio.sleep(IDLE_SECONDS)
        for pid in list(self._count):
            self._start(pid)

    def _start(self, pid: int) -> None:
        t = asyncio.create_task(self._write(pid))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """会話が終わるとき：まだメモにしていない分を書く"""
        if self._timer is not None:
            self._timer.cancel()
        await asyncio.gather(*(self._write(pid) for pid in list(self._count)), return_exceptions=True)

    async def _write(self, pid: int) -> None:
        lock = self._locks.setdefault(pid, asyncio.Lock())
        async with lock:
            start, end = self._done.get(pid, 0), len(self.lines)
            if not any(p == pid for p, _, _ in self.lines[start:end]):
                return
            store = self.book.store
            k = next((k for k in self.book.known if k.person_id == pid), None)
            if store is None or k is None or not k.notes_ok:
                return
            window = self.lines[max(0, end - CONTEXT_LINES):end]
            existing = await store.notes(pid)
            request = {
                'today': datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d（%a）'),
                'person': k.name,
                'existing_notes': [{'id': i, 'text': t} for i, t in existing],
                'conversation': [{'speaker': who, 'is_person': p == pid, 'text': text} for p, who, text in window],
            }
            try:
                r = await self._client.chat.completions.create(
                    model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'},
                    messages=[{'role': 'system', 'content': self.instructions},
                              {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
                result = json.loads(r.choices[0].message.content or '{}')
            except Exception as e:   # メモが書けなくても、会話は続ける
                log.warning('メモを書けない：%s', type(e).__name__)
                return
            valid = {i for i, _ in existing}
            add = [t.strip()[:MAX_NOTE_CHARS] for t in result.get('add', []) if isinstance(t, str) and t.strip()]
            update = {int(u['id']): u['text'].strip()[:MAX_NOTE_CHARS] for u in result.get('update', [])
                      if isinstance(u, dict) and u.get('id') in valid and isinstance(u.get('text'), str) and u['text'].strip()}
            delete = [int(i) for i in result.get('delete', []) if i in valid and i not in update]
            if add or update or delete:
                await store.change_notes(pid, add, update, delete)
                k.note_count = await store.count_notes(pid)
            self._done[pid], self._count[pid] = end, 0
            log.info('メモ #%d：足す %d・直す %d・消す %d（全 %d）', pid, len(add), len(update), len(delete), k.note_count)


def ciel_text(text: str) -> str:
    """シエルの返事から、感情の印と [silent] を外す"""
    text = emotion.strip_tags(text).replace('[silent]', '').strip()
    return text
