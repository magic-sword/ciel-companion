# -*- coding: utf-8 -*-
"""いまのシエル：心・道具・体の、いまの動きを 1 か所に集めてアプリへ送る（activity.state、topic ciel.event）。

なぜ：心が道具を呼ばずに止まっているのか、ゲームに頼んで答えを待っているのか、体が技をしている最中なのかが、
外から分からず、止まって見えた（2026-11-07）。アプリの「いま」の札とパネル（CielConversationUI.Activity.cs）が読む。

- 心：考えている（心・小脳）・話している・聞いている。LiveKit の agent_state と、返事を作る pipeline（agent.py）から。
- 呼んでいる道具：心が呼ぶと決めた道具（llm_node の道具の呼び出し）から、結果が返るまで（function_tools_executed）。
- 体の技：時間のかかる技（ゲームの ciel/long_running）を始めてから、終わりの知らせ（task_done）まで（game_env.py）。
  目的の係が体で進めている段も入れる（goals.py の body_step）。
- 最近のこと：道具の結果（始めなかった・できた）、技の終わり、心への知らせ（言葉だけで止まった など）。新しいものが先。
- 送るのは、変わったときだけ（PUBLISH_GAP にまとめる）。経った秒数は、送ったときの値をアプリが数え足す。
- ゲームの名前は知らない（道具の見せる名前は、ゲーム・アプリの道具の title から）。
"""
import asyncio
import itertools
import json
import time
from collections import deque
from typing import Callable

VERSION = 1
PUBLISH_GAP = 0.25   # これより短い間の変化は、まとめて 1 回で送る
LOG_KEEP = 12
TEXT_CHARS = 120


def _short(text: str) -> str:
    text = ' '.join(str(text or '').split())
    return text if len(text) <= TEXT_CHARS else text[:TEXT_CHARS - 1] + '…'


class Activity:
    def __init__(self, notify: Callable[[dict], None] | None, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.notify = notify
        self._clock = clock
        self.mind = 'idle'                # idle・listening・thinking・speaking
        self.who: str | None = None       # 考えている係（mind：心・talker：小脳）
        self.thinking_origin = ''
        self._mind_epoch = 0
        self.background_thinking = False
        self._background_at = clock()
        self._background_epoch = 0
        self._mind_at = clock()
        self._calls: dict[str, dict] = {}     # call_id → {name, label, at}
        self._body: dict = {}
        self._body_at = clock()
        self._finished: dict[str, bool] = {}
        self._tasks: dict[str, dict] = {}     # 技の鍵 → {title, at}（体でしている技）
        self._log: deque = deque(maxlen=LOG_KEEP)
        self.titles: dict[str, str] = {}      # 道具の名前 → 見せる名前（ゲーム・アプリの道具の title）
        self.body_doing: Callable[[], str | None] = lambda: None   # 体がいましていること（ゲームの様子の doing）
        self.goal_step: Callable[[], str | None] = lambda: None    # 目的の係が体で進めている段（goals.py の body_step）
        self._ids = itertools.count(1)
        self._pending: asyncio.Handle | None = None
        self._shown = ''

    # ---- 心 ----

    def agent_state(self, ev) -> None:
        """LiveKit の agent_state_changed（listening・thinking・speaking など）"""
        state = str(getattr(ev, 'new_state', '') or '')
        if state == 'thinking' and self.mind == 'thinking':
            return
        self._set_mind(state if state in ('listening', 'thinking', 'speaking') else 'idle')

    def thinking(self, who: str, origin: str = '') -> None:
        """返事を作り始めた（心か小脳か）"""
        self.who, self.thinking_origin = who, origin
        self._mind_epoch += 1
        self._mind_at = self._clock()
        self._set_mind('thinking')
        self.changed()

    def background(self, active: bool) -> None:
        """内なる考えを生成している間だけ。考えの本文は送らない。"""
        if self.background_thinking != active:
            self.background_thinking, self._background_at = active, self._clock()
            self._background_epoch += 1
            self.changed()

    def _set_mind(self, state: str) -> None:
        if state != self.mind:
            self.mind, self._mind_at = state, self._clock()
            if state != 'thinking':
                self.who = None
                self.thinking_origin = ''
            self.changed()

    # ---- 道具 ----

    def label(self, name: str) -> str:
        return self.titles.get(name) or name

    def call_started(self, call_id: str, name: str) -> None:
        """心が道具を呼ぶと決めた（結果が返るまで「呼んでいる」）"""
        if call_id and call_id not in self._calls:
            self._calls[call_id] = {'name': name, 'label': self.label(name), 'at': self._clock()}
            self.changed()

    def tools_executed(self, ev) -> None:
        """LiveKit の function_tools_executed：道具の結果が返った"""
        for call, out in zip(getattr(ev, 'function_calls', []) or [], getattr(ev, 'function_call_outputs', []) or []):
            started = self._calls.pop(getattr(call, 'call_id', ''), None)
            name = getattr(call, 'name', '') or (started or {}).get('name', '')
            self._result(name, getattr(out, 'output', '') if out is not None else '',
                         bool(getattr(out, 'is_error', False)) if out is not None else True)
        self.changed()

    def _result(self, name: str, output: str, is_error: bool) -> None:
        label = self.label(name)
        try:
            r = json.loads(output) if output else {}
        except (TypeError, ValueError):
            r = {}
        r = r if isinstance(r, dict) else {}
        status = r.get('status')
        if is_error or status in ('error', 'tool_failed'):
            self.log(f'{label}：始めなかった（{r.get("why") or r.get("reason") or "うまくいかなかった"}）', 'error')
        elif status in ('unavailable', 'no_answer', 'busy', 'goal_running'):
            why = {'unavailable': '体とつながっていない', 'no_answer': '答えが無い', 'busy': 'ほかの会話が体を使っている',
                   'goal_running': r.get('why') or '目的の係が体を使っている'}[status]
            self.log(f'{label}：{why}', 'wait')
        elif status == 'started':
            self.log(f'{label}：始めた（{r.get("title") or r.get("goal") or ""}）'.replace('（）', ''), 'ok')
        elif status == 'accepted':
            self.log(f'{label}：依頼を受け付けた（体の開始待ち）', 'info')
        elif status == 'already_doing':
            self.log(f'{label}：もうしている', 'info')

    # ---- 体の技 ----

    def task_started(self, key: str, title: str) -> None:
        if key in self._finished:
            return
        if key in self._tasks:
            return
        self._tasks[key] = {'title': title, 'at': self._clock()}
        self.changed()

    def task_done(self, key: str, title: str, ok: bool, note: str | None = None, quiet: bool = False) -> None:
        if key in self._finished:
            return
        self._finished[key] = True
        if len(self._finished) > 512:
            self._finished.pop(next(iter(self._finished)))
        self._tasks.pop(key, None)
        if not quiet:
            self.log(f'体：{title}' + ('（できた）' if ok else f'（できなかった：{note}）' if note else '（できなかった）'),
                     'ok' if ok else 'error')
        self.changed()

    def set_body(self, state: dict) -> None:
        self._body = dict(state)
        self._body_at = self._clock()
        self.changed()

    # ---- 最近のこと ----

    def log(self, text: str, kind: str = 'info') -> None:
        """kind：ok（できた・始めた）・error（できなかった）・wait（待っている・断った）・info（知らせ）"""
        self._log.appendleft({'id': next(self._ids), 'at': self._clock(), 'text': _short(text), 'kind': kind})
        self.changed()

    # ---- 送る ----

    def state(self) -> dict:
        now = self._clock()
        try:
            doing = self.body_doing()
        except Exception:
            doing = None
        try:
            step = self.goal_step()
        except Exception:
            step = None
        return {
            'v': VERSION, 'type': 'activity.state',
            'mind': self.mind, 'who': self.who or '', 'mind_for': round(now - self._mind_at, 1),
            'detail_version': 1, 'thinking_origin': self.thinking_origin,
            'mind_epoch': self._mind_epoch, 'background_epoch': self._background_epoch,
            'background_thinking': self.background_thinking,
            'background_for': round(now - self._background_at, 1) if self.background_thinking else 0,
            'calls': [{'label': c['label'], 'for_s': round(now - c['at'], 1)} for c in self._calls.values()],
            'tasks': [] if self._body else [{'title': t['title'], 'for_s': round(now - t['at'], 1)} for t in self._tasks.values()],
            'body': {**self._body, 'for_s': round(self._body.get('for_s', 0) + now - self._body_at, 1)} if self._body else None,
            'doing': doing or '', 'goal_step': step or '',
            'log': [{'id': e['id'], 'ago': round(now - e['at'], 1), 'text': e['text'], 'kind': e['kind']} for e in self._log],
        }

    def changed(self) -> None:
        """変わった：少しまとめてから送る（ループが無ければ、すぐ送る）"""
        if self.notify is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.publish()
            return
        if self._pending is None:
            self._pending = loop.call_later(PUBLISH_GAP, self.publish)

    def publish(self) -> None:
        self._pending = None
        if self.notify is None:
            return
        s = self.state()
        # 経った秒数だけが違うなら送らない（アプリが数え足す）
        shown = json.dumps({k: v for k, v in s.items() if k not in ('mind_for', 'background_for')} | {
            'body': {k: v for k, v in (s.get('body') or {}).items() if k != 'for_s'},
            'calls': [c['label'] for c in s['calls']], 'tasks': [t['title'] for t in s['tasks']],
            'log': [e['id'] for e in s['log']]}, ensure_ascii=False, sort_keys=True)
        if shown == self._shown:
            return
        self._shown = shown
        self.notify(s)
