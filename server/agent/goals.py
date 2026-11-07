# -*- coding: utf-8 -*-
"""目的の係：長い目的（「石のつるはしを作る」）を、心の外の決まった流れで最後までやり遂げる。docs/goal-runner-design-ja.md。

- 流れ：計画（ゲームの係の plan）→ 段を 1 つずつ実行（run）→ 結果で確かめる（check）→ だめなら決まった直し方（repair。
  計画し直し）→ それでもだめなら心に相談 → 同じ段で何度もだめなら止めて持ち主に聞く。
- 目的は木にできる（6 章）。段が失敗して決まった直し方が無いとき、心が小さな目標（add_subgoal）を作る。小さな目標が
  できたら、親の失敗した段からやり直す。深さは決め打ちしない。ループは「同じ目標が先祖にいる」「進んでいない」「予算」で止める。
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
# 小さな目標のループの止め方（深さは決め打ちしない。ADaPT は深いほど成功が上がった。docs/long-horizon-planning-research-ja.md の 5 章）
MAX_SUBGOALS = 12     # 1 つの目的の中で、失敗から作る小さな目標の合計
MAX_DEPTH = 8         # 壊れたとき用の大きな上限（ふつうは届かない）
BUDGET_SECONDS = 30 * 60   # 1 つの目的にかける時間
MAX_STILL = 2         # 小さな目標の前後で何も変わらない（持ち物・場所）ことが、続けてここまであれば止める
ACTIVE = ('planning', 'running', 'paused', 'waiting')


@dataclass
class Step:
    id: int
    kind: str                     # ゲームの係が決める（マイクラ：gather・craft・find・mind）
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
    status: str = 'planning'      # planning・running・paused・waiting（小さな目標を待つ）・done・failed・stopped
    steps: list[Step] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    attention: str | None = None  # 止まっている理由（持ち主・心に聞いていること）
    parent: 'Goal | None' = None  # 小さな目標なら、親の目的
    parent_step: Step | None = None   # 親のどの段のための小さな目標か（できたら、その段からやり直す）
    started_at: float = 0.0
    subgoals: int = 0             # いちばん上の目的だけ：作った小さな目標の数
    still: int = 0                # いちばん上の目的だけ：何も変わらなかった小さな目標が続いた数
    before: object = None         # 小さな目標を始めたときの様子（ゲームの係の snapshot）

    @property
    def depth(self) -> int:
        return 0 if self.parent is None else self.parent.depth + 1

    @property
    def root(self) -> 'Goal':
        return self if self.parent is None else self.parent.root

    def chain(self) -> list['Goal']:
        """いちばん上の目的から、この目標まで"""
        return ([] if self.parent is None else self.parent.chain()) + [self]


def _key(title: str, spec: dict) -> str:
    """同じ目標かどうか（作る物があれば物の名前、無ければ見せる言葉）"""
    make = (spec or {}).get('make')
    return f'make:{make}' if make else 'title:' + ''.join(title.split())


class GoalRunner:
    def __init__(self, say: Callable[..., None], publish: Callable[[dict], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.say = say                # mouth.Mouth.say_latest（why, settle=, instructions=, merge=）
        self.publish = publish        # アプリと配信の画面へ（goal.state）
        self.adapters: dict[str, object] = {}
        self.labels: dict[str, str] = {}   # ゲームの見せる名前（マイクラ）
        self.goal: Goal | None = None      # いちばん上の目的
        self.active: Goal | None = None    # 今進めている目標（小さな目標があれば、いちばん下）
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
        # 止まっている目的と同じ物をもう一度頼まれた：あとに並べず、計画からやり直す
        # （心が計画し直そうとして start_goal を呼び、「あとで」に並んだだけで止まったままだった。2026-11-07）
        again = (self.active is not None and self.active.status == 'paused'
                 and _key(title, spec) == _key(self.goal.title, self.goal.spec))
        if self.goal is not None and self.goal.status in ACTIVE and not first and not again:
            self.next.append({'game': game, 'title': title, 'spec': spec, 'why': why, 'by': by})
            self._publish()
            return {'status': 'queued', 'after': self.goal.title}
        if self.goal is not None and self.goal.status in ACTIVE:
            await self.stop(keep_next=True, reason='replaced')
        goal = Goal(next(self._ids), game, title, by, spec, why, started_at=self._clock())
        self.goal = self.active = goal
        self._publish()
        r = await self._plan(goal)
        if r is not None:
            return r
        debug_log.record('goal', what='start', id=goal.id, title=title, steps=[s.label for s in goal.steps])
        self._publish()
        self._run()
        return {'status': 'started', 'goal': title, 'steps': [s.label for s in goal.steps]}

    async def add_subgoal(self, title: str, spec: dict, *, why: str = '') -> dict:
        """今の目標の止まっている段のために、小さな目標を作る（できたら、その段からやり直す）"""
        cur = self.active
        if cur is None or cur.status not in ('paused', 'running'):
            return {'status': 'no_goal'}
        step = self._stuck_step(cur)
        if step is None:
            return {'status': 'no_stuck_step', 'why': '止まっている段が無い（小さな目標は、段が止まったときに作る）'}
        root = cur.root
        refused = self._refuse(cur, title, spec)
        if refused is not None:
            debug_log.record('goal', what='subgoal_refused', id=cur.id, title=title, reason=refused['reason'])
            if refused['reason'] != 'loop':   # 予算・深さ：持ち主に聞く（ループなら、心に別の手を考えてもらう）
                self._pause(cur, step, refused['why'], ask_owner=True, count=False)
            return refused
        if self._task is not None and not self._task.done() and step.kind != 'mind':
            await self.adapters[cur.game].stop()   # 体の技の途中なら止める
        self._cancel()
        root.subgoals += 1
        if step.status == 'running':
            step.status = 'todo'
        cur.status = 'waiting'
        cur.attention = f'先に「{title}」'
        sub = Goal(next(self._ids), cur.game, title, 'ciel', spec, why, parent=cur, parent_step=step,
                   started_at=self._clock(), before=self._snapshot(cur.game))
        self.active = sub
        r = await self._plan(sub)
        if r is not None:   # 計画できない：親に戻して止める
            self.active = cur
            cur.status = 'paused'
            cur.attention = f'「{title}」を計画できない（{r.get("why") or r.get("reason")}）'
            self._publish()
            return r
        self._change(cur, f'「{step.label}」のために、先に「{title}」をする')
        debug_log.record('goal', what='subgoal', id=sub.id, parent=cur.id, title=title, depth=sub.depth,
                         steps=[s.label for s in sub.steps])
        self._publish()
        self._run()
        return {'status': 'started', 'subgoal': title, 'for': step.label, 'path': [g.title for g in sub.chain()],
                'steps': [s.label for s in sub.steps]}

    async def stop(self, *, keep_next: bool = False, reason: str = 'stopped', only_current: bool = False) -> dict:
        g = self.active
        if g is None or g.status not in ACTIVE:
            return {'status': 'no_goal'}
        if only_current and g.parent is not None:   # 小さな目標だけやめて、親で止まって待つ
            self._cancel()
            await self.adapters[g.game].stop()
            g.status = 'stopped'
            parent = g.parent
            self.active = parent
            parent.status = 'paused'
            parent.attention = f'「{g.title}」をやめた'
            debug_log.record('goal', what='stop_subgoal', id=g.id, reason=reason)
            self._publish()
            return {'status': 'stopped', 'goal': g.title, 'back_to': parent.title}
        for x in g.chain():
            x.status = 'stopped'
            x.attention = None
        self._cancel()
        await self.adapters[g.game].stop()
        if not keep_next:
            self.next.clear()
        debug_log.record('goal', what='stop', id=self.goal.id, reason=reason)
        self._publish()
        return {'status': 'stopped', 'goal': self.goal.title}

    def resume(self) -> dict:
        g = self.active
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
        g = self.active
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

    async def _plan(self, goal: Goal) -> dict | None:
        """段を決める。決められなければ、目的を failed にして道具の返事を返す"""
        steps = await self.adapters[goal.game].plan(goal)
        if steps is None:   # ゲームの係では分けられない目的：心が進める段 1 つにする
            steps = [{'kind': 'mind', 'args': {'text': goal.title}, 'label': goal.title}]
        if isinstance(steps, dict):   # 計画できない（{'error': …}）
            goal.status = 'failed'
            goal.attention = steps.get('why') or steps.get('error')
            self._publish()
            return {'status': 'error', 'reason': steps.get('error'), 'why': steps.get('why')}
        goal.steps = [self._step(s) for s in steps]
        goal.status = 'running'
        return None

    def _refuse(self, cur: Goal, title: str, spec: dict) -> dict | None:
        """小さな目標を作らない理由（ループ・予算・深さ）。作ってよければ None"""
        root = cur.root
        key = _key(title, spec)
        if any(_key(g.title, g.spec) == key for g in cur.chain()):
            return {'status': 'refused', 'reason': 'loop',
                    'why': f'「{title}」は、もう上の目標にある（同じことのために同じことをする輪になる）。別の手を考える'}
        if root.subgoals >= MAX_SUBGOALS:
            return {'status': 'refused', 'reason': 'budget', 'why': f'小さな目標を {MAX_SUBGOALS} 個作っても終わらない'}
        if self._clock() - root.started_at >= BUDGET_SECONDS:
            return {'status': 'refused', 'reason': 'budget', 'why': f'{BUDGET_SECONDS // 60} 分たっても終わらない'}
        if cur.depth + 1 > MAX_DEPTH:
            return {'status': 'refused', 'reason': 'depth', 'why': '小さな目標が深くなりすぎた'}
        return None

    @staticmethod
    def _stuck_step(g: Goal) -> Step | None:
        return next((s for s in g.steps if s.status in ('failed', 'running')), None)

    def _snapshot(self, game: str):
        snap = getattr(self.adapters[game], 'snapshot', None)
        try:
            return snap() if snap is not None else None
        except Exception:
            return None

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
        g = self.active
        try:
            while g is not None and g.status == 'running':
                adapter = self.adapters[g.game]
                step = next((s for s in g.steps if s.status in ('todo', 'running')), None)
                if step is None:
                    g = await self._done(g)   # 小さな目標なら親へ戻る（親を続ける）
                    continue
                step.status = 'running'
                self._publish()
                if step.kind == 'mind':
                    result = await self._ask_mind(g, step)
                else:
                    result = await adapter.run(g, step)
                if g.status != 'running' or self.active is not g:
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
                self._pause(g, step, why, ask_owner=step.fails >= MAX_FAILS)
                return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ERRORS.report('goals', e, kind='task')   # 記録とアプリへの知らせ（errors.py）
            g = self.active
            if g is not None:
                g.status = 'paused'
                g.attention = 'うまくいかなかった'
            self._publish()

    async def _done(self, g: Goal) -> Goal | None:
        """目標ができた。小さな目標なら親の段へ戻り、親を返す（続ける）。いちばん上なら終える"""
        g.status = 'done'
        debug_log.record('goal', what='done', id=g.id)
        parent = g.parent
        if parent is not None:
            root = g.root
            still = g.before is not None and self._snapshot(g.game) == g.before
            root.still = root.still + 1 if still else 0
            self.active = parent
            step = g.parent_step
            if step is not None and step.status != 'done':
                step.status = 'todo'
            if root.still >= MAX_STILL:   # 小さな目標を終えても何も変わらない：ループかもしれないので止めて聞く
                self._pause(parent, step or parent.steps[0], '小さな目標を終えても、持ち物も場所も変わらない', ask_owner=True,
                            count=False)
                return None
            parent.status = 'running'
            parent.attention = None
            self._change(parent, f'「{g.title}」ができたので、「{step.label if step else parent.title}」に戻る')
            self._tell(f'[目的「{root.title}」：小さな目標「{g.title}」ができた。「{parent.title}」の続きに戻る]')
            self._publish()
            return parent
        self._publish()
        self._tell(f'[目的「{g.title}」ができた]')
        if self.next:
            n = self.next.pop(0)
            await self.start(n['game'], n['title'], n['spec'], why=n['why'], by=n['by'])
        return None

    async def _ask_mind(self, g: Goal, step: Step) -> dict:
        self._mind_step = asyncio.get_running_loop().create_future()
        self._tell(f'[目的「{g.title}」：次の段「{step.label}」は、自分で考えて進める。体の道具で進め、'
                   'できたら finish_step(ok=true)、できなければ finish_step(ok=false)。'
                   '途中で手が足りなければ add_subgoal で小さな目標を作れる]')
        try:
            r = await self._mind_step
        finally:
            self._mind_step = None
        return {'ok': r['ok'], 'reason': None if r['ok'] else 'mind_failed', 'note': {'text': r.get('note', '')}}

    def _pause(self, g: Goal, step: Step, why: str, *, ask_owner: bool, count: bool = True) -> None:
        if count:
            step.status = 'failed'
        g.status = 'paused'
        g.attention = f'「{step.label}」ができない（{why}）'
        debug_log.record('goal', what='paused', id=g.id, step=step.label, fails=step.fails, why=why)
        self._publish()
        path = ' › '.join(x.title for x in g.chain())
        if ask_owner:
            times = f'{step.fails} 回うまくいかなかった' if count else 'うまくいかない'
            self._tell(f'[目的「{path}」：「{step.label}」が{times}（{why}）。'
                       '止めて待っている。どうしたいか持ち主に聞く]')
        else:
            self._tell(f'[目的「{path}」：「{step.label}」ができない（{why}）。なぜできないかを考え、それを片づける小さな目標を'
                       ' add_subgoal で作る（できたら自動でこの段に戻る。例：置く場所が無い → 「広い場所へ移る」）。'
                       'ほかの道具で直したなら resume_goal。やめるなら stop_goal。自分で手が無ければ持ち主に相談する]')

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
        g = self.active
        if g is None or g.status not in ACTIVE:
            return None
        done = sum(1 for s in g.steps if s.status == 'done')
        now = next((s for s in g.steps if s.status in ('running', 'failed', 'todo')), None)
        part = ''
        if now is not None:
            prog = f' {now.progress[0]}/{now.progress[1]}' if now.progress else ''
            part = f'（{done}/{len(g.steps)}：{now.label}{prog}）'
        line = '[今の目的] ' + ' › '.join(x.title for x in g.chain()) + part
        if g.status == 'paused':
            line += f' 止まっている：{g.attention}'
        if self.next:
            line += '。あとで：' + '、'.join(n['title'] for n in self.next)
        return line

    def state(self) -> dict:
        root, g = self.goal, self.active
        if root is None or g is None:
            return {'v': VERSION, 'type': 'goal.state', 'goal': None, 'path': [], 'steps': [], 'changes': [], 'next': [],
                    'attention': None}
        public = self.presence() == 'public'
        try:
            name = None if public else self.owner_name()
        except Exception:   # 呼び名が読めなくても、目的は見せる（呼び名の読み違いで目的の係ごと止まった。2026-11-07）
            name = None
        # 画面には、いちばん上の目的の名前と、今いる目標までの道筋、今の目標の段を出す
        status = g.status if g.status != 'done' or g is root else root.status
        return {
            'v': VERSION, 'type': 'goal.state',
            'goal': {'id': root.id, 'game': root.game, 'game_label': self.labels.get(root.game, root.game), 'title': root.title,
                     'by': root.by, 'by_label': (f'{name}のお願い' if name else '持ち主のお願い') if root.by == 'owner' else 'シエルが決めた',
                     'status': 'running' if status == 'waiting' else status, 'why': root.why},
            'path': [x.title for x in g.chain()],
            'steps': [{'id': s.id, 'label': s.label, 'status': s.status, 'progress': s.progress} for s in g.steps],
            'changes': [c['text'] for c in g.changes] or [c['text'] for c in root.changes],
            'next': [n['title'] for n in self.next],
            'attention': g.attention,
        }

    def _publish(self) -> None:
        if self.publish is not None:
            self.publish(self.state())
