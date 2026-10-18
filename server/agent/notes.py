# -*- coding: utf-8 -*-
"""その人について覚えておくメモを、会話の裏で書く（会話を止めない）。

- 書くきっかけは 2 つ。
  1. 会話モデル（Realtime API）が道具 remember_about_speaker で「これを覚えて」と 1 文を預ける
     （道具はすぐ戻り、返事を作り直さないので、会話は止まらない）。
  2. 会話の流れから、道具で拾い漏れたことを補う。
  どちらも、今のメモと突き合わせて足す・書き直す・消すを決めるのは、別の文字のモデル
  （既定 gpt-5.4-mini、CIEL_NOTES_MODEL）に裏で任せる。
- 会話の文字起こしと話者は共通履歴（conversation.py）から読む。独自の全文は持たない。
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

import speakers
from conversation import Conversation, Turn

log = logging.getLogger('ciel-agent.notes')

MODEL = os.environ.get('CIEL_NOTES_MODEL', 'gpt-5.4-mini')
TURNS = 4            # 同意した人がこの回数話したら書く
IDLE_SECONDS = 40    # 同意した人が話してから、この秒数だれも話さなければ書く
CONTEXT_LINES = 30   # 1 回に渡す会話の行数（ほかの人の発言も、文脈として含める）
MAX_NOTE_CHARS = 120


class NoteTaker:
    def __init__(self, book: speakers.SpeakerBook, instructions: str, history: Conversation) -> None:
        self.book = book
        self.instructions = instructions
        self.history = history
        self._done: dict[int, int] = {}                       # 人ごとに、どこまでメモにしたか（発言 ID）
        self._count: dict[int, int] = {}
        self._requested: dict[int, list[str]] = {}         # 会話モデルが道具で預けたメモ（まだ書いていない）
        self._forgets: dict[int, list[str]] = {}           # 本人に「忘れて」と頼まれたこと（まだ消していない）
        self.forgotten: dict[int, list[str]] = {}          # この会話で頼まれた「忘れて」のすべて（関係の係も使う）
        self._locks: dict[int, asyncio.Lock] = {}
        self._timer: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._client = openai.AsyncOpenAI()

    def on_turn(self, turn: Turn) -> None:
        """相手の発言の文字起こし（確定したもの）と、その発言の話者の判定（シエルへの [発言者：…] と同じもの）"""
        if turn.role != 'user' or not turn.text:
            return
        # 発言した人（この会話の話者）を、同意の前でも付けておく（メモリーの中だけ）。
        # この会話の途中で名乗って同意した人も、同意の前に話したこと（「ミルクティーが好き」など）を
        # メモにできるように（覚えたあとは sp.person_id が付く）。書くのは同意してから（_write が確かめる）。
        # 「たぶん」の発言・短くて決められなかった発言は、誰の発言か確かでないので、誰の発言にもしない
        owner = turn.owner
        if owner is None or owner.person_id is None:
            return
        k = next((k for k in self.book.known if k.person_id == owner.person_id), None)
        if k is None or not k.notes_ok:
            return
        pid = k.person_id
        if turn.id <= self._done.get(pid, 0):
            # 待機上限を超えてから届いた発言も、次の更新で拾い直す。
            self._done[pid] = turn.id - 1
        self._count[pid] = self._count.get(pid, 0) + 1
        if self._count[pid] >= TURNS:
            self._start(pid)
        else:
            self._arm_timer()

    def _arm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.create_task(self._idle())

    async def _idle(self) -> None:
        await asyncio.sleep(IDLE_SECONDS)
        for pid in list(self._count):
            self._start(pid)

    def request(self, pid: int, note: str) -> None:
        """会話モデルが道具（remember_about_speaker）で「これを覚えて」と渡した：すぐ裏で書く"""
        note = note.strip()[:MAX_NOTE_CHARS]
        if not note:
            return
        self._requested.setdefault(pid, []).append(note)
        self._count.setdefault(pid, 0)
        log.info('メモ #%d：会話モデルから 1 件預かった', pid)
        self._start(pid)

    def forget(self, pid: int, what: str) -> None:
        """本人に「○○のことは忘れて」「それは別の人の話」と頼まれた（道具 forget_about_speaker）：すぐ裏で消す。
        どのメモが当てはまるかは、記録係のモデルが中身で決める（番号を読み上げて確かめなくてよいように）"""
        what = what.strip()[:MAX_NOTE_CHARS]
        if not what:
            return
        self._forgets.setdefault(pid, []).append(what)
        self.forgotten.setdefault(pid, []).append(what)
        self._count.setdefault(pid, 0)
        log.info('メモ #%d：忘れる依頼を 1 件預かった', pid)
        self._start(pid)

    def on_consent(self, pid: int) -> None:
        """この会話の途中で、お話を覚えることに同意した：同意の前に話したことも含めて、すぐ書く"""
        self._count.setdefault(pid, 0)
        self._start(pid)

    def _start(self, pid: int) -> None:
        t = asyncio.create_task(self._write(pid))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        """会話が終わるとき：まだメモにしていない分を書く"""
        if self._timer is not None:
            self._timer.cancel()
        while self._tasks:
            tasks = list(self._tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.difference_update(tasks)
        await asyncio.gather(*(self._write(pid) for pid in list(self._count)), return_exceptions=True)
        while self._tasks:
            tasks = list(self._tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.difference_update(tasks)

    async def _write(self, pid: int) -> None:
        lock = self._locks.setdefault(pid, asyncio.Lock())
        async with lock:
            start, end = self._done.get(pid, 0), self.history.settled_through()
            turns = self.history.between(start, end)
            requested = self._requested.pop(pid, [])
            forgets = self._forgets.pop(pid, [])
            if (not requested and not forgets
                    and not any(t.owner is not None and t.owner.person_id == pid for t in turns)):
                return
            store = self.book.store
            k = next((k for k in self.book.known if k.person_id == pid), None)
            if store is None or k is None or not k.notes_ok:
                return
            # 人数が多くても、未処理分を直近30行で飛ばさない。上限つきで順に処理する。
            batch = turns[:CONTEXT_LINES]
            if batch:
                end = batch[-1].id
            window = [(t.owner, t.name, t.text) for t in self.history.between(through=end)[-CONTEXT_LINES:]
                      if t.ready.is_set() and t.text]
            existing = await store.notes(pid)
            request = {
                'today': datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d（%a）'),
                'person': k.name,
                'existing_notes': [{'id': i, 'text': t} for i, t in existing],
                'requested_notes': requested,
                'forget_requests': list(dict.fromkeys([*self.forgotten.get(pid, []), *forgets])),
                'conversation': [{'speaker': who, 'is_person': o is not None and o.person_id == pid, 'text': text}
                                 for o, who, text in window],
            }
            try:
                r = await self._client.chat.completions.create(
                    model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'},
                    messages=[{'role': 'system', 'content': self.instructions},
                              {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
                result = json.loads(r.choices[0].message.content or '{}')
            except Exception as e:   # メモが書けなくても、会話は続ける（頼まれた分は次の機会に回す）
                log.warning('メモを書けない：%s', type(e).__name__)
                self._requested.setdefault(pid, [])[:0] = requested
                self._forgets.setdefault(pid, [])[:0] = forgets
                return
            valid = {i for i, _ in existing}
            add = [t.strip()[:MAX_NOTE_CHARS] for t in result.get('add', []) if isinstance(t, str) and t.strip()]
            update = {int(u['id']): u['text'].strip()[:MAX_NOTE_CHARS] for u in result.get('update', [])
                      if isinstance(u, dict) and u.get('id') in valid and isinstance(u.get('text'), str) and u['text'].strip()}
            delete = [int(i) for i in result.get('delete', []) if i in valid and i not in update]
            if add or update or delete:
                await store.change_notes(pid, add, update, delete)
                k.note_count = await store.count_notes(pid)
            current = self._done.get(pid, 0)
            self._done[pid] = min(end, current) if current != start else end
            self._count[pid] = sum(t.owner is not None and t.owner.person_id == pid
                                   for t in self.history.between(end))
            if any(t.owner is not None and t.owner.person_id == pid
                   for t in self.history.between(self._done[pid], self.history.settled_through())):
                self._start(pid)
            log.info('メモ #%d：足す %d・直す %d・消す %d（全 %d）', pid, len(add), len(update), len(delete), k.note_count)
