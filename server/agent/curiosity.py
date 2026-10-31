# -*- coding: utf-8 -*-
"""気になったことを、シエルが自分で調べる（CIEL_MODEL=pipeline）。

内なる考え（initiative.py）の「調べてみたいこと」は、それまで「気になるのです」と興味を言うだけだった（決定記録の第 2 段階）。
ここでは、気持ちの強い「調べてみたいこと」を、シエルが話の裏で Web で調べ（web_research.py。頼まれた調べものと同じ係）、
分かったら知らせとして話す。時間ではなく、気になった・分かったという出来事で話す。
- 受ける考え：種類が research、気持ち MIN_MOTIVATION 以上、考える係が調べる質問（query。個人的なことは入れない。
  config/prompts/inner_thoughts.md）を書いたもの。initiative.py の sync_board が渡す。断ったら「気になっている」の付箋のまま。
- 断るとき：ひかえめ（会議）・止めている間（声の登録・歌）・別の調べものの最中・1 時間に PER_HOUR 回を超えた（料金のため）。
- 調べているあいだは「気になって調べている」の付箋（board.py）。アプリには、頼まれた調べものと同じ調査のパネルが届く。
- 分かったら、口の知らせ（mouth.py の say_latest、why は research）で、話の切れ目に言う。相手への返事を先に作るときは、
  心がその返事の中で伝える（mind.py の [まだ伝えていない知らせ]）。言い方は config/prompts/research_found.md。
- 調べられなかったら、話さない（付箋は失敗にし、その考えは気持ちを下げて残す）。
ログには数と状態だけを出す（質問・結果の中身は debug_log）。
"""
import asyncio
import json
import logging
import os
import time
from collections import deque

import board as tasks
import debug_log

log = logging.getLogger('ciel-agent.curiosity')

MIN_MOTIVATION = 4.0
PER_HOUR = int(os.environ.get('CIEL_CURIOSITY_PER_HOUR', '3'))
SETTLE = 1.2           # 知らせは、相手がこの秒数だまってから言う（議事録の知らせと同じ）
SUMMARY_CHARS = 1500   # 知らせに渡す結果の文字数


class Curiosity:
    def __init__(self, researcher, board: tasks.Board, say, instructions: str, *, style=None,
                 paused=None, clock=time.monotonic) -> None:
        self.researcher = researcher    # web_research.WebResearcher
        self.board = board
        self.say = say                  # 知らせを言う（instructions を受ける。agent.py が mouth.say_latest につなぐ）
        self.instructions = instructions   # config/prompts/research_found.md
        self.style = style              # mode.ConversationStyle
        self.paused = paused            # 呼ぶと True のあいだは調べない（声の登録・歌）
        self._clock = clock
        self._started: deque[float] = deque()
        self._task: asyncio.Task | None = None
        self._capped: set[str] = set()   # 上限で断った考えの id

    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def offer(self, thought) -> bool:
        """内なる考えを調べるか。受けたら True（調べ始める）"""
        query = getattr(thought, 'query', '').strip()
        if (thought.kind != 'research' or thought.motivation < MIN_MOTIVATION or not query or not self.instructions
                or self.busy() or self.researcher is None):
            return False
        if (self.style is not None and self.style.talk == 'quiet') or (self.paused is not None and self.paused()):
            return False
        lock = getattr(self.researcher, '_lock', None)
        if lock is not None and lock.locked():
            return False   # 頼まれた調べものの最中
        now = self._clock()
        while self._started and now - self._started[0] >= 3600:
            self._started.popleft()
        if len(self._started) >= PER_HOUR:
            if thought.id not in self._capped:   # 見回りのたびに呼ばれるので、1 つの考えにつき 1 回だけ残す
                self._capped.add(thought.id)
                log.info('気になったこと：1 時間の上限（%d 回）なので調べない', PER_HOUR)
                debug_log.record('curiosity_capped', thought=thought.text)
            return False
        self._started.append(now)
        thought.researching = True   # 気になっている付箋には載せない（initiative.py の board_thoughts）
        self._task = asyncio.create_task(self._research(thought, query))
        return True

    async def _research(self, thought, query: str) -> None:
        card = self.board.add('research', f'{thought.text}（気になって調べている）', tasks.RUNNING, 'self', ref=thought.id)
        log.info('気になったこと：自分から調べ始めた')
        debug_log.record('curiosity_start', thought=thought.text, query=query)
        try:
            result = await self.researcher.search(query, f'self-{thought.id}', None)
        except Exception as e:   # 調べられなくても、会話は続ける
            log.warning('気になったこと：調べられない：%s', type(e).__name__)
            result = {'status': 'failed'}
        status = result.get('status') if isinstance(result, dict) else None
        thought.researching = False
        debug_log.record('curiosity_done', status=status, summary=result.get('summary') if status == 'completed' else None)
        if status != 'completed':
            self.board.move(card, tasks.FAILED, note='調べられなかった')
            thought.query = ''   # 同じことを調べ直さない。気になっていることとしては残す
            thought.motivation = max(1.0, thought.motivation - 1.0)
            return
        self.board.move(card, tasks.DONE, note='分かったので、話の切れ目に伝える')
        thought.expressed = True   # 分かったことは知らせで話す（気になっている付箋には戻さない）
        found = {'thought': thought.text, 'question': query,
                 'summary': (result.get('summary') or '')[:SUMMARY_CHARS],
                 'sources': [s.get('title') for s in result.get('sources') or [] if isinstance(s, dict)][:3]}
        self.say(self.instructions + '\n\n' + json.dumps(found, ensure_ascii=False))
