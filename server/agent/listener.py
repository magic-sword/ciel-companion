# -*- coding: utf-8 -*-
"""聞く係（CIEL_MODEL=pipeline）：話の途中の頼みごとを、文字起こしの区切りごとに見つけて、コードが直接動かす。

それまでは、議事録を始める・終えるのは、会話モデルが返事のときに道具を選んだときだけだった。長く話し続けると、話し終えるまで
頼みが届かず（約 16 秒）、ひかえめでは名前を呼ばないと届かず、道具を呼ばずに「始めました」と答えることもあった（2026-10-30、
bench_compare.py）。ここでは、文字起こしが区切られるたび（話の途中でも、息つぎごとに届く）に：
1. 頼みの言葉（WORDS）があるかを見る（お金はかからない）。
2. あれば、軽いモデル（config/prompts/listener.md）に、前後の発言と議事録の状態を渡して、シエルへの頼みか・何の頼みかを確かめる。
3. 頼みなら、議事録をコードが始める・終える（道具 start_minutes・finish_minutes と同じ処理）。シエルの一言は、議事録係の知らせ
   （agent.py の on_minutes）が、話の切れ目に言わせる。
確かめているあいだは「確認中」の付箋（board.py）を出し、頼みだったら、その発言を議事録の付箋に結び付ける。心と小脳は、
その発言を付箋の状態の印で読むので、同じ頼みを受け直さない。頼みでなければ、付箋を外す。
今は議事録の始める・終えるだけ。ログには頼みの種類だけを出す（発言の中身は debug_log）。
"""
import asyncio
import json
import logging
import re
import time

import openai

import board as tasks
import debug_log
import models

log = logging.getLogger('ciel-agent.listener')

# 「議事録」は「二次録」などと書き起こされることがあるので、「録」で見る（頼みかは軽いモデルが確かめる）
WORDS = re.compile(r'録|まとめ')
CONTEXT_TURNS = 6
TIMEOUT = 10.0
COOLDOWN = 20.0     # 同じ頼みを続けて動かさない秒数（「議事録開始して」「議事録とってね」と言い直したとき）


class Listener:
    def __init__(self, history, minutes, instructions: str, client=None, board=None) -> None:
        self.history = history        # conversation.Conversation
        self.minutes = minutes        # minutes.Minutes
        self.instructions = instructions   # config/prompts/listener.md
        self.board = board            # board.Board（確認中の付箋と、頼みの発言の結び付け）
        self._client = client
        self._done: dict[str, float] = {}  # 頼みの種類 → 動かした時刻
        self._tasks: set[asyncio.Task] = set()

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    async def settled(self, timeout: float) -> None:
        """確かめている頼みがあれば、終わるまで（timeout 秒まで）待つ。返事を作る前に待ち、聞く係と心が同じ頼みを同時に
        受けないようにする（心が道具で始め直して「もうとっている」が返り、知らせの一言が「もうとっているのです」になった。2026-10-30）"""
        if self._tasks:
            await asyncio.wait(set(self._tasks), timeout=timeout)

    def on_transcribed(self, ev) -> None:
        """文字起こしが区切られた（LiveKit の user_input_transcribed の確定）"""
        if not ev.is_final or not ev.transcript or not WORDS.search(ev.transcript) or not self.instructions:
            return
        task = asyncio.create_task(self.check(ev.transcript))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def check(self, text: str) -> str | None:
        """頼みかを確かめて、頼みなら動かす。動かした頼みの種類（start・finish）を返す"""
        card = (self.board.add('minutes', '議事録の頼みかを確かめる', tasks.CHECKING, 'listener', said=text)
                if self.board is not None else None)
        try:
            action = await self._check(text)
        finally:
            if card is not None and card.status == tasks.CHECKING:
                self.board.remove(card)   # 頼みでなかった（始めたときは、議事録係がこの付箋を実行中にしている）
        if action is not None and self.board is not None:
            target = self.board.find('minutes', statuses=(*tasks.ACTIVE, tasks.DONE, tasks.FAILED))
            if target is not None:
                self.board.said(target, text)
        return action

    async def _check(self, text: str) -> str | None:
        recent = [{'speaker': t.name, 'text': t.text[:400]} for t in
                  [t for t in self.history.turns if t.ready.is_set() and t.text][-CONTEXT_TURNS:]] if self.history else []
        request = {'latest': text[:400], 'recent': recent, 'recording': bool(getattr(self.minutes, 'recording', False))}
        model = models.model('listener')
        try:
            r = await self.client.chat.completions.create(
                model=model, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=TIMEOUT,
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            models.record('listener', model, getattr(r, 'usage', None))
            result = json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 確かめられなくても、会話は続ける（会話モデルが道具で受けることもできる）
            log.warning('聞く係：頼みを確かめられない：%s', type(e).__name__)
            return None
        return self.act(result, time.monotonic())

    def act(self, result, now: float) -> str | None:
        action = result.get('action') if isinstance(result, dict) else None
        if action not in ('start', 'finish') or result.get('to_ciel') is False:
            return None
        if now - self._done.get(action, -1e9) < COOLDOWN:
            return None
        self._done[action] = now
        if action == 'start':
            template = result.get('template') if result.get('template') in ('meeting', 'goals', 'research') else 'meeting'
            status = self.minutes.start(0, template, by='listener')
        else:
            status = self.minutes.finish(by='listener')
        log.info('聞く係：話の途中の頼みで議事録を動かした（%s → %s）', action, status)
        debug_log.record('listener_action', action=action, status=status)
        return action
