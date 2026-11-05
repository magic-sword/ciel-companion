# -*- coding: utf-8 -*-
"""マイクラの体（server/minecraft）へつなぐ係。docs/minecraft-design-ja.md の 4.3・5 章。

- 体は会話とは別に動き続ける。会話の始めにこの係が ws でつなぎ、会話が終わったら切る（体はその場で待つ）。
  体を動かせる会話は 1 つだけで、ほかの会話がつないでいれば体は busy で断る。
- 最新の様子を持ち、心と小脳へ「[マイクラの様子]」として渡す（context）。
- 出来事は全部届く。話すものだけをコードで選び（モデルを使わない）、口（mouth.py）の why 'game' で、話の切れ目に知らせる。
  どう話すかは config/prompts/minecraft.md。
- つなぐ先は環境変数 CIEL_MINECRAFT_URL（例 ws://127.0.0.1:8768）。空ならつながない（道具も心に渡さない。mind.py）。
"""
import asyncio
import itertools
import json
import logging
import os
import time
from typing import Callable

import websockets

import debug_log

log = logging.getLogger('ciel-agent.minecraft')

URL = os.environ.get('CIEL_MINECRAFT_URL', '')
VERSION = 1
START_TIMEOUT = 3.0       # 技を頼んでから「始めた」が返るまでの上限
RETRY_MIN, RETRY_MAX = 3.0, 30.0
BIG_HURT = 4              # 一度にこれだけ減ったら言う（体力は 20 まで）
LOW_HEALTH = 6
SAME_KIND_SECONDS = 30.0  # 同じ種類の知らせは、この秒数に 1 回まで
URGENT_SETTLE = 0.3       # 危ない知らせは、すぐの切れ目で言う
SETTLE = 1.2              # ふつうの知らせは、相手がこの秒数だまってから言う
INVENTORY_SHOWN = 6

# 終わり方（体の done の reason）ごとの知らせ。止めた・ほかの技に替えたときは言わない
FAIL_LINES = {
    'player_not_visible': 'の相手が見えなくなった（遠い・別の場所にいる）',
    'no_owner': 'の相手が分からない（持ち主のプレイヤー名が設定されていない）',
    'not_found': 'ができなかった。近くに見つからない',
    'cannot_harvest': 'ができなかった。道具が無くて掘れない',
    'not_spawned': 'ができなかった。まだマイクラに入っていない',
    'died': 'の途中で倒れた',
    'error': 'の途中でうまくいかなくなった',
}
QUIET_REASONS = ('stopped', 'replaced', 'unlinked', 'disconnected')
SKILL_NAMES = {'follow': 'ついていく', 'come': 'そばへ行く', 'go_to': '場所へ行く', 'collect': '集める'}


class Body:
    def __init__(self, url: str, say: Callable[..., None], *, diary=None) -> None:
        self.url = url
        self.say = say               # mouth.Mouth.say_latest（why, settle=, instructions=）
        self.diary = diary           # diary.Diary（倒した・倒れたなど、本当にあったことを残す）
        self.linked = False          # 体とつながっている（hello を受けた）
        self.state: dict | None = None
        self.owner: str | None = None
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._skills: dict[int, str] = {}   # 頼んだ技（id → 技の名前）。done には技の名前が無い
        self._remembered: set[str] = set()  # この会話で日記に残した出来事（同じ敵を何体倒しても 1 回）
        self._said: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._closed = False

    # ---- つなぐ ----

    def start(self) -> None:
        if self.url and self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        retry = RETRY_MIN
        while not self._closed:
            try:
                async with websockets.connect(self.url, open_timeout=5) as ws:
                    self._ws = ws
                    async for raw in ws:
                        self.on_message(raw)
                        retry = RETRY_MIN
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info('マイクラの体へつなげない：%s', type(e).__name__)
            finally:
                self._ws = None
                if self.linked:
                    log.info('マイクラの体から切れた')
                self.linked = False
                for f in self._pending.values():
                    if not f.done():
                        f.set_result({'status': 'unavailable'})
                self._pending.clear()
            if self._closed:
                return
            await asyncio.sleep(retry)
            retry = min(retry * 2, RETRY_MAX)

    def on_message(self, raw) -> None:
        try:
            m = json.loads(raw)
        except (TypeError, ValueError):
            return
        kind = m.get('type')
        if kind == 'hello':
            self.linked, self.owner, self.state = True, m.get('owner'), m.get('state')
            log.info('マイクラの体とつながった')
            debug_log.record('minecraft', what='linked')
        elif kind == 'busy':
            log.info('マイクラの体は、ほかの会話が使っている')
        elif kind == 'state':
            self.state = m
        elif kind in ('started', 'error'):
            f = self._pending.pop(m.get('id'), None)
            if f is not None and not f.done():
                f.set_result({'status': 'started'} if kind == 'started' else {'status': 'error', 'reason': m.get('reason')})
        elif kind == 'done':
            self.on_done(m)
        elif kind == 'event':
            self.on_event(m)

    # ---- 頼む（道具 tools/minecraft.py から） ----

    async def do(self, skill: str, args: dict | None = None) -> dict:
        """技を頼む。始めたか（started）を返す。終わったら、知らせで話す（on_done）"""
        if not self.linked or self._ws is None:
            return {'status': 'unavailable'}
        id_ = next(self._ids)
        f = asyncio.get_running_loop().create_future()
        self._pending[id_] = f
        self._skills[id_] = skill
        await self._send({'type': 'do', 'id': id_, 'skill': skill, 'args': args or {}})
        try:
            return await asyncio.wait_for(f, START_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(id_, None)
            return {'status': 'no_answer'}

    async def stop(self) -> dict:
        if not self.linked or self._ws is None:
            return {'status': 'unavailable'}
        await self._send({'type': 'stop'})
        return {'status': 'stopped'}

    async def _send(self, msg: dict) -> None:
        try:
            await self._ws.send(json.dumps({'v': VERSION, **msg}, ensure_ascii=False))
        except Exception as e:
            log.info('マイクラの体へ送れない：%s', type(e).__name__)

    # ---- 様子 ----

    def context(self) -> str | None:
        """心と小脳へ渡す「[マイクラの様子]」（つなぐ先が無ければ None）"""
        if not self.url:
            return None
        s = self.state
        if not self.linked:
            return '[マイクラの様子]\nシエルの体とつながっていない（マイクラの中のことは分からない）'
        if not s or not s.get('connected'):
            return '[マイクラの様子]\nシエルはマイクラに入っていない（入り直しているところ）'
        inv = sorted((s.get('inventory') or {}).items(), key=lambda kv: -kv[1])[:INVENTORY_SHOWN]
        doing = s.get('doing')
        me = [f"体力 {round(s.get('health') or 0)}/20", f"空腹 {s.get('food')}/20",
              '持ち物 ' + ('、'.join(f'{k}×{n}' for k, n in inv) if inv else 'なし'),
              'していること ' + (SKILL_NAMES.get(doing['skill'], doing['skill']) if doing else 'なし')]
        when = ('夜（敵が出る）' if s.get('night') else '昼') + ('・雨' if s.get('raining') else '')
        near = [f"{p['name']}{'（持ち主）' if p['name'] == self.owner else ''} {p['distance']} ブロック"
                for p in s.get('players') or []]
        near += [f"{h['name']} {h['distance']} ブロック" for h in s.get('hostiles') or []]
        lines = ['[マイクラの様子]', 'シエル：' + '・'.join(me), f'時刻：{when}', '近く：' + ('、'.join(near) if near else 'だれもいない')]
        if self.owner and not any(p['name'] == self.owner for p in s.get('players') or []):
            lines.append(f'{self.owner}（持ち主）は近くにいない')
        return '\n'.join(lines)

    # ---- 出来事を選んで話す（docs/minecraft-design-ja.md の 5 章） ----

    def on_done(self, m: dict) -> None:
        skill = SKILL_NAMES.get(self._skills.pop(m.get('id'), ''), '技')
        if m.get('ok'):
            gained = (m.get('note') or {}).get('gained')
            if gained:   # 集め終えた。そばへ行く・場所へ行くは、着いたのが見えるので言わない
                got = '、'.join(f'{k}×{n}' for k, n in gained.items())
                self._tell('done', f'[マイクラ：頼まれたものを集め終えた（{got}）]', SETTLE, limit=False)
            return
        reason = m.get('reason') or 'error'
        if reason in QUIET_REASONS or reason == 'died':   # 倒れたことは died の出来事で言う
            return
        what = FAIL_LINES.get(reason, FAIL_LINES['error'])
        self._tell('failed', f'[マイクラ：頼まれた「{skill}」{what}]', SETTLE, limit=False)

    def on_event(self, m: dict) -> None:
        kind = m.get('kind')
        if kind == 'died':
            self._remember('マイクラで倒れた')
            self._tell(kind, '[マイクラ：シエルが倒れた（初めの場所で生き返った。持ち物は落とした）]', URGENT_SETTLE)
        elif kind == 'owner_died':
            self._tell(kind, f'[マイクラ：{self.owner or "持ち主"}が倒れた]', URGENT_SETTLE)
        elif kind == 'flee':
            self._tell(kind, f"[マイクラ：{m.get('from')}から逃げている（体力 {m.get('health')}/20）]", URGENT_SETTLE)
        elif kind == 'hurt':
            amount, health = m.get('amount') or 0, m.get('health') or 0
            if amount >= BIG_HURT or (health <= LOW_HEALTH and amount > 0):
                self._tell(kind, f'[マイクラ：{amount} のダメージを受けた（体力 {health}/20）]', URGENT_SETTLE)
        elif kind == 'defeated':
            self._remember(f"マイクラで {m.get('name')} を倒した")
            self._tell(kind, f"[マイクラ：{m.get('name')}を倒した]", SETTLE)
        elif kind in ('spawned', 'disconnected'):
            debug_log.record('minecraft', what=kind)
        # 夜・天気・プレイヤーの出入り・チャットは様子に入るだけ（チャットは B4）

    def _tell(self, kind: str, line: str, settle: float, *, limit: bool = True) -> None:
        now = time.monotonic()
        if limit and now - self._said.get(kind, -SAME_KIND_SECONDS) < SAME_KIND_SECONDS:
            return
        self._said[kind] = now
        debug_log.record('minecraft', what=kind)
        context = self.context()
        self.say('game', settle=settle, instructions=line + ('\n\n' + context if context else ''))

    def _remember(self, text: str) -> None:
        if self.diary is not None and text not in self._remembered:
            self._remembered.add(text)
            try:
                self.diary.add('minecraft', text)
            except Exception as e:
                log.info('日記に書けない：%s', type(e).__name__)
