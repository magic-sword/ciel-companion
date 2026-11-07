# -*- coding: utf-8 -*-
"""目的の係：長い目的（「石のつるはしを作る」）を、心の外の決まった流れで最後までやり遂げる。docs/goal-runner-design-ja.md。

- 流れ：計画（ゲームの係の plan）→ 段を 1 つずつ実行（run）→ 結果で確かめる（check）→ だめなら決まった直し方（repair。
  計画し直し）→ それでもだめなら心に相談 → 同じ段で何度もだめなら止めて持ち主に聞く。
- ゲームを知らない。ゲームごとの係（adapter）が、段の中身・実行・確かめ方・見せる言葉を持つ（マイクラは minecraft.py の Goals）。
- 「できた」は確かめた結果で決める。心の言葉では決めない（「作り始めました」と言ったあと体が断っても、目的の段は正しい）。
- 心へは、会話の後ろにいつも短く「[今の目的]」を渡す。口（mouth.py）の知らせは区切りだけ（始めた・直した・相談・できた）。
- 今の目的と段は、変わるたびにアプリと配信の画面へ goal.state で送る（topic ciel.goal）。
- 心の自発は残す：目的を始めるのは、持ち主の頼みでもシエル自身の思いつきでもよい（道具 start_goal）。
- 会話をまたいで続ける（DB に置く）のは、あとで足す（今はこの会話の中だけ）。
"""
import asyncio
import itertools
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import debug_log
from errors import ERRORS

log = logging.getLogger('ciel-agent.goals')

TOPIC = 'ciel.goal'
VERSION = 1
SETTLE = 1.2
MAX_REPAIRS = 3       # 決まった直し方で計画し直すのは、同じ段でここまで
MAX_FAILS = 3         # 同じ段でここまでうまくいかなければ、止めて持ち主に聞く
CHANGES_SHOWN = 3
STOPPED_BY_OTHERS = ('stopped', 'replaced', 'unlinked', 'disconnected', 'died')   # 段の失敗ではなく、止められた


@dataclass
class Step:
    id: int
    kind: str                     # ゲームの係が決める（マイクラ：gather・craft・mind）
    args: dict
    label: str
    status: str = 'todo'          # todo・running・done・failed・skipped
    progress: list | None = None  # [できた数, 目標の数]（数で確かめられる段だけ）
    fails: int = 0
    repairs: int = 0


@dataclass
class Goal:
    id: int
    game: str
    title: str
    by: str                       # owner（持ち主の頼み）・ciel（シエルの思いつき）
    spec: dict                    # ゲームの係に渡す目的の中身（マイクラ：{'make': 'stone_pickaxe', 'count': 1}）
    why: str = ''
    status: str = 'planning'      # planning・running・paused・done・failed・stopped
    steps: list[Step] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    attention: str | None = None  # 止まっている理由（持ち主・心に聞いていること）


class GoalRunner:
    def __init__(self, say: Callable[..., None], publish: Callable[[dict], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.say = say                # mouth.Mouth.say_latest（why, settle=, instructions=, merge=）
        self.publish = publish        # アプリと配信の画面へ（goal.state）
        self.adapters: dict[str, object] = {}
        self.labels: dict[str, str] = {}   # ゲームの見せる名前（マイクラ）
        self.goal: Goal | None = None
        self.next: list[dict] = []    # あとでやる目的（start_goal の引数）
        self._clock = clock
        self._ids = itertools.count(1)
        self._step_ids = itertools.count(1)
        self._task: asyncio.Task | None = None
        self._mind_step: asyncio.Future | None = None
        self.presence: Callable[[], str] = lambda: 'solo'   # 人前なら、頼んだ人の名前を出さない
        self.owner_name: Callable[[], str | None] = lambda: None   # 持ち主の呼び名（speakers.py）

    def register(self, game: str, adapter, label: str) -> None:
        self.adapters[game] = adapter
        self.labels[game] = label

    # ---- 心の道具から ----

    async def start(self, game: str, title: str, spec: dict, *, why: str = '', by: str = 'owner', first: bool = False) -> dict:
        adapter = self.adapters.get(game)
        if adapter is None or not adapter.available():
            return {'status': 'unavailable'}
        if self.goal is not None and self.goal.status in ('planning', 'running', 'paused') and not first:
            self.next.append({'game': game, 'title': title, 'spec': spec, 'why': why, 'by': by})
            self._publish()
            return {'status': 'queued', 'after': self.goal.title}
        if self.goal is not None and self.goal.status in ('planning', 'running', 'paused'):
            await self.stop(keep_next=True, reason='replaced')
        goal = Goal(next(self._ids), game, title, by, spec, why)
        self.goal = goal
        self._publish()
        steps = await adapter.plan(goal)
        if steps is None:   # ゲームの係では分けられない目的：心が進める段 1 つにする（心が分けるのは、あとで足す）
            steps = [{'kind': 'mind', 'args': {'text': title}, 'label': title}]
        if isinstance(steps, dict):   # 計画できない（{'error': …}）
            goal.status = 'failed'
            goal.attention = steps.get('why') or steps.get('error')
            self._publish()
            return {'status': 'error', 'reason': steps.get('error'), 'why': steps.get('why')}
        goal.steps = [self._step(s) for s in steps]
        goal.status = 'running'
        debug_log.record('goal', what='start', id=goal.id, title=title, steps=[s.label for s in goal.steps])
        self._publish()
        self._run()
        return {'status': 'started', 'goal': title, 'steps': [s.label for s in goal.steps]}

    async def stop(self, *, keep_next: bool = False, reason: str = 'stopped') -> dict:
        g = self.goal
        if g is None or g.status not in ('planning', 'running', 'paused'):
            return {'status': 'no_goal'}
        g.status = 'stopped'
        g.attention = None
        self._cancel()
        await self.adapters[g.game].stop()
        if not keep_next:
            self.next.clear()
        debug_log.record('goal', what='stop', id=g.id, reason=reason)
        self._publish()
        return {'status': 'stopped', 'goal': g.title}

    def resume(self) -> dict:
        g = self.goal
        if g is None or g.status != 'paused':
            return {'status': 'not_paused'}
        g.status = 'running'
        g.attention = None
        for s in g.steps:
            if s.status in ('running', 'failed'):
                s.status = 'todo'
        self._publish()
        self._run()
        return {'status': 'resumed', 'goal': g.title}

    def finish_step(self, ok: bool, note: str = '') -> dict:
        """心に任せた段（mind）を終える"""
        if self._mind_step is None or self._mind_step.done():
            return {'status': 'no_mind_step'}
        self._mind_step.set_result({'ok': ok, 'note': note})
        return {'status': 'ok'}

    def status(self) -> dict:
        return self.state()

    def pause_for(self, reason: str) -> None:
        """持ち主が「止まって」と言った・体がほかの技を始めた（今の段をやめる。目的は止めて待つ）"""
        g = self.goal
        if g is not None and g.status == 'running':
            g.status = 'paused'
            g.attention = reason
            self._cancel()
            self._publish()

    def on_data(self, packet) -> None:
        """アプリの「止める」「続ける」（topic ciel.goal の goal.control）"""
        if getattr(packet, 'topic', None) != TOPIC:
            return
        try:
            m = json.loads(packet.data.decode('utf-8'))
        except (ValueError, AttributeError, UnicodeDecodeError):
            return
        if not isinstance(m, dict) or m.get('type') != 'goal.control':
            return
        if m.get('action') == 'stop':
            asyncio.create_task(self.stop())
        elif m.get('action') == 'resume':
            self.resume()

    # ---- 流れ ----

    def _run(self) -> None:
        self._cancel()
        self._task = ERRORS.spawn(self._loop(), 'goals')

    def _cancel(self) -> None:
        if self._task is not None and not self._task.done() and self._task is not asyncio.current_task():
            self._task.cancel()
        self._task = None
        if self._mind_step is not None and not self._mind_step.done():
            self._mind_step.cancel()
        self._mind_step = None

    async def _loop(self) -> None:
        g = self.goal
        adapter = self.adapters[g.game]
        try:
            while g.status == 'running':
                step = next((s for s in g.steps if s.status in ('todo', 'running')), None)
                if step is None:
                    await self._done(g)
                    return
                step.status = 'running'
                self._publish()
                if step.kind == 'mind':
                    result = await self._ask_mind(g, step)
                else:
                    result = await adapter.run(g, step)
                if g.status != 'running':
                    return
                ok, progress = adapter.check(g, step, result)
                step.progress = progress
                if ok:
                    step.status = 'done'
                    continue
                reason = (result or {}).get('reason') or 'error'
                if reason in STOPPED_BY_OTHERS:   # 止められた・倒れた・切れた：目的は止めて待つ（段の失敗に数えない）
                    step.status = 'todo'
                    g.status = 'paused'
                    g.attention = adapter.why(reason)
                    self._publish()
                    return
                step.fails += 1
                if step.repairs < MAX_REPAIRS:
                    repaired = await adapter.repair(g, step, result)
                    if repaired is not None:
                        steps, text = repaired
                        step.repairs += 1
                        done = [s for s in g.steps if s.status == 'done']
                        g.steps = done + [self._step(s, repairs=step.repairs) for s in steps]
                        self._change(g, text)
                        self._tell(f'[目的「{g.title}」：{text}。続けている]')
                        continue
                why = adapter.why(reason, result)
                if step.fails >= MAX_FAILS:
                    self._pause(g, step, why, ask_owner=True)
                    return
                self._pause(g, step, why, ask_owner=False)
                return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ERRORS.report('goals', e, kind='task')   # 記録とアプリへの知らせ（errors.py）
            g.status = 'paused'
            g.attention = 'うまくいかなかった'
            self._publish()

    async def _done(self, g: Goal) -> None:
        g.status = 'done'
        debug_log.record('goal', what='done', id=g.id)
        self._publish()
        self._tell(f'[目的「{g.title}」ができた]')
        if self.next:
            n = self.next.pop(0)
            await self.start(n['game'], n['title'], n['spec'], why=n['why'], by=n['by'])

    async def _ask_mind(self, g: Goal, step: Step) -> dict:
        self._mind_step = asyncio.get_running_loop().create_future()
        self._tell(f'[目的「{g.title}」：次の段「{step.label}」は、自分で考えて進める。'
                   'できたら finish_step(ok=true)、できなければ finish_step(ok=false)]')
        try:
            r = await self._mind_step
        finally:
            self._mind_step = None
        return {'ok': r['ok'], 'reason': None if r['ok'] else 'mind_failed', 'note': {'text': r.get('note', '')}}

    def _pause(self, g: Goal, step: Step, why: str, *, ask_owner: bool) -> None:
        step.status = 'failed'
        g.status = 'paused'
        g.attention = f'「{step.label}」ができない（{why}）'
        debug_log.record('goal', what='paused', id=g.id, step=step.label, fails=step.fails)
        self._publish()
        if ask_owner:
            self._tell(f'[目的「{g.title}」：「{step.label}」が {step.fails} 回うまくいかなかった（{why}）。'
                       '止めて待っている。どうしたいか持ち主に聞く]')
        else:
            self._tell(f'[目的「{g.title}」：「{step.label}」ができない（{why}）。手を変えるなら、ほかの道具で用意してから'
                       ' resume_goal で続ける。やめるなら stop_goal。自分で手が無ければ持ち主に相談する]')

    def _change(self, g: Goal, text: str) -> None:
        g.changes.append({'at': self._clock(), 'text': text})
        g.changes = g.changes[-CHANGES_SHOWN:]
        debug_log.record('goal', what='repair', id=g.id, text=text)
        self._publish()

    def _step(self, s: dict, repairs: int = 0) -> Step:
        return Step(next(self._step_ids), s['kind'], s.get('args') or {}, s['label'],
                    progress=s.get('progress'), repairs=repairs)

    def _tell(self, line: str) -> None:
        self.say('game', settle=SETTLE, instructions=line, merge=True)

    # ---- 見せる ----

    def context(self) -> str | None:
        """会話の後ろに渡す「[今の目的]」（無ければ None）"""
        g = self.goal
        if g is None or g.status not in ('planning', 'running', 'paused'):
            return None
        done = sum(1 for s in g.steps if s.status == 'done')
        now = next((s for s in g.steps if s.status in ('running', 'failed', 'todo')), None)
        part = ''
        if now is not None:
            prog = f' {now.progress[0]}/{now.progress[1]}' if now.progress else ''
            part = f'（{done}/{len(g.steps)}：{now.label}{prog}）'
        line = f'[今の目的] {g.title}{part}'
        if g.status == 'paused':
            line += f' 止まっている：{g.attention}'
        if self.next:
            line += '。あとで：' + '、'.join(n['title'] for n in self.next)
        return line

    def state(self) -> dict:
        g = self.goal
        if g is None:
            return {'v': VERSION, 'type': 'goal.state', 'goal': None, 'steps': [], 'changes': [], 'next': [], 'attention': None}
        public = self.presence() == 'public'
        try:
            name = None if public else self.owner_name()
        except Exception:   # 呼び名が読めなくても、目的は見せる（呼び名の読み違いで目的の係ごと止まった。2026-11-07）
            name = None
        return {
            'v': VERSION, 'type': 'goal.state',
            'goal': {'id': g.id, 'game': g.game, 'game_label': self.labels.get(g.game, g.game), 'title': g.title,
                     'by': g.by, 'by_label': (f'{name}のお願い' if name else '持ち主のお願い') if g.by == 'owner' else 'シエルが決めた',
                     'status': g.status, 'why': g.why},
            'steps': [{'id': s.id, 'label': s.label, 'status': s.status, 'progress': s.progress} for s in g.steps],
            'changes': [c['text'] for c in g.changes],
            'next': [n['title'] for n in self.next],
            'attention': g.attention,
        }

    def _publish(self) -> None:
        if self.publish is not None:
            self.publish(self.state())
