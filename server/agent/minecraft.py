# -*- coding: utf-8 -*-
"""マイクラの体（server/minecraft）へつなぐ係。docs/minecraft-design-ja.md の 4.3・5 章。

- 体は会話とは別に動き続ける。会話の始めにこの係が ws でつなぎ、会話が終わったら切る（体はその場で待つ）。
  体を動かせる会話は 1 つだけで、ほかの会話がつないでいれば体は busy で断る。
- 最新の様子を持ち、心と小脳へ「[マイクラの様子]」として渡す（context）。
- つなぐのは、アプリの設定「マイクラで一緒に遊ぶ」がオンのときだけ（topic ciel.game の game.link。on_data）。
  体とつながったか・マイクラに入っているかは、アプリへ game.state で知らせる（つながらない理由：busy・connecting・off・unavailable）。
- 出来事は全部届く。話すものだけをコードで選び（モデルを使わない）、口（mouth.py）の why 'game' で、話の切れ目に知らせる。
  どう話すかは config/prompts/minecraft.md。
- つなぐ先は環境変数 CIEL_MINECRAFT_URL（例 ws://127.0.0.1:8768）。空ならつながない（道具も心に渡さない。mind.py）。
  空のときにアプリがオンにしたら、unavailable と返す（refuse）。
- 目：頼まれたら（道具 look_at_view）体に景色を 1 枚撮ってもらい（look → seen）、目の係（eyes.py）に渡す。
  道具の返事の続きで、心がその絵を見て話す。docs/minecraft-vision-design-ja.md。
"""
import asyncio
import base64
import binascii
import itertools
import json
import logging
import os
import time
from typing import Callable

import websockets

import board as tasks
import debug_log

log = logging.getLogger('ciel-agent.minecraft')

URL = os.environ.get('CIEL_MINECRAFT_URL', '')
TOPIC = 'ciel.game'
VERSION = 1
START_TIMEOUT = 3.0       # 技を頼んでから「始めた」が返るまでの上限
LOOK_TIMEOUT = 25.0       # 景色を頼んでから絵が返るまでの上限（初めはブラウザを開いて描き終えるまで 10 秒ほど）
FACING = {'north': '北', 'northwest': '北西', 'west': '西', 'southwest': '南西', 'south': '南', 'southeast': '南東',
          'east': '東', 'northeast': '北東'}
RETRY_MIN, RETRY_MAX = 3.0, 30.0
BIG_HURT = 4              # 一度にこれだけ減ったら言う（体力は 20 まで）
LOW_HEALTH = 6
SAME_KIND_SECONDS = 30.0  # 同じ種類の知らせは、この秒数に 1 回まで
URGENT_SETTLE = 0.3       # 危ない知らせは、すぐの切れ目で言う
SETTLE = 1.2              # ふつうの知らせは、相手がこの秒数だまってから言う
INVENTORY_SHOWN = 6
BLOCKS_SHOWN = 8

# 終わり方（体の done の reason）ごとの知らせ。止めた・ほかの技に替えたときは言わない
# うまくいかなかった理由（体の done の reason）。知らせ・付箋に使う。（ ）の前が付箋の短いひとこと
WHY_FAILED = {
    'player_not_visible': '相手が見えない（遠い・別の場所にいる）',
    'no_owner': '相手が分からない（持ち主のプレイヤー名が設定されていない）',
    'not_found': '見える所に無い（今いる所から見えない・まだ見ていない。地中に埋まっている物は分からない）',
    'cannot_harvest': '掘れない（その道具を持っていない）',
    'needs_tool': '掘る道具が無い（素手では取れない）',
    'unknown_block': 'そういう名前のブロックが無い',
    'unknown_item': 'そういう名前の物が無い',
    'cannot_craft': '作れない物（作り方が無い）',
    'missing_materials': '材料が足りない',
    'no_table': '作業台が要る（近くに無く、持ってもいない）',
    'no_room': '作業台を置く場所が無い',
    'no_path': 'そこまでの道が見つからない（遠い・高い・水や崖の向こう）',
    'not_spawned': 'マイクラに入っていない',
    'not_have': 'その物を持っていない',
    'cannot_dig': '足元が掘れないブロック（建物に使うもの・素手では掘れないもの）',
    'danger': 'すぐ下が溶岩か水で危ない',
    'died': '途中で倒れた',
    'unlinked': '体から切れた',
    'disconnected': 'マイクラから出た',
    'error': 'うまくいかなかった',
}
QUIET_REASONS = ('stopped', 'replaced', 'unlinked', 'disconnected')
SKILL_NAMES = {'follow': 'ついていく', 'come': 'そばへ行く', 'go_to': '場所へ行く', 'collect': '集める', 'give': '渡す',
               'dig_down': '足元を掘って降りる', 'craft': '作る'}


def title(skill: str, args: dict) -> str:
    """付箋の題（「oak_log を 10 個集める」）"""
    who = args.get('player') or '持ち主'
    if skill == 'follow':
        return f'{who}についていく'
    if skill == 'come':
        return f'{who}のそばへ行く'
    if skill == 'go_to':
        return f"{who}のところへ行く" if 'player' in args else f"（{args.get('x')}, {args.get('z')}）へ行く"
    if skill == 'collect':
        return f"{args.get('block')} を {args.get('count', 1)} 個集める"
    if skill == 'dig_down':
        return f"足元を {args['depth']} ブロック掘る" if 'depth' in args else '足元を掘って降りる'
    if skill == 'craft':
        return f"{args.get('item')} を {args.get('count', 1)} 個作る"
    if skill == 'give':
        return f"{args.get('item')} を{' ' + str(args['count']) + ' 個' if 'count' in args else ''}{who}に渡す"
    return skill


def reasons(reason: str, note: dict) -> str:
    """うまくいかなかった理由の文（足りない材料・要る道具も添える）"""
    why = WHY_FAILED.get(reason, WHY_FAILED['error'])
    if note.get('needs'):
        why += '（足りない物：' + '、'.join(f'{k}×{n}' for k, n in note['needs'].items()) + '）'
    if note.get('tool'):
        why += f"（要る道具：{note['tool']} 以上）"
    return why


def refused(m: dict) -> dict:
    """体が始める前に断った（error）。理由の文も添え、心が道具の返事を見て、その場で正直に言えるようにする"""
    reason = m.get('reason')
    r = {'status': 'error', 'reason': reason}
    if reason in WHY_FAILED:
        r['why'] = reasons(reason, m.get('note') or {})
    return r


def _link_wanted(packet) -> bool | None:
    if getattr(packet, 'topic', None) != TOPIC:
        return None
    try:
        m = json.loads(packet.data.decode('utf-8'))
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    return bool(m.get('on')) if isinstance(m, dict) and m.get('type') == 'game.link' else None


def refuse(notify: Callable[[dict], None]) -> Callable:
    """つなぐ先の無い会話サーバー：アプリがオンにしたら、つなげないと返す"""
    def on_data(packet) -> None:
        if _link_wanted(packet):
            notify({'v': VERSION, 'type': 'game.state', 'linked': False, 'in_world': False, 'reason': 'unavailable'})
    return on_data


class Body:
    def __init__(self, url: str, say: Callable[..., None], *, diary=None, board=None,
                 notify: Callable[[dict], None] | None = None) -> None:
        self.url = url
        self.say = say               # mouth.Mouth.say_latest（why, settle=, instructions=）
        self.diary = diary           # diary.Diary（倒した・倒れたなど、本当にあったことを残す）
        self.board = board           # board.Board（頼まれた技を付箋にする。同じ頼みを二重に受けない）
        self.notify = notify         # アプリへの知らせ（game.state）
        self.eyes = None             # eyes.Eyes（撮った景色を渡す先。agent.py が置く）
        self.reason = 'off'          # つながっていない理由（off・connecting・busy）
        self._shown: tuple | None = None
        self._cards: dict[int, object] = {}   # 技の id → 付箋
        self.linked = False          # 体とつながっている（hello を受けた）
        self.state: dict | None = None
        self.owner: str | None = None
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._asked: dict[int, str] = {}    # 頼んだ技（id → 付箋の題）。done には技の名前が無い
        self._fails: dict[str, int] = {}    # 同じ頼み（題）が続けてうまくいかなかった回数。できたら消す
        self._remembered: set[str] = set()  # この会話で日記に残した出来事（同じ敵を何体倒しても 1 回）
        self._said: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._closed = False

    # ---- つなぐ ----

    def on_data(self, packet) -> None:
        """アプリの設定「マイクラで一緒に遊ぶ」（game.link）。オンでつなぎ、オフで切る（体はその場で待つ）"""
        on = _link_wanted(packet)
        if on is True:
            self.start()
        elif on is False:
            asyncio.create_task(self.close())

    def start(self) -> None:
        if not self.url or (self._task is not None and not self._task.done()):
            self.publish()
            return
        self._closed = False
        self.reason = 'connecting'
        self._task = asyncio.create_task(self._run())
        self.publish()

    async def close(self) -> None:
        self._closed = True
        self.reason = 'off'
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.publish()

    def publish(self) -> None:
        """体とつながったか・マイクラに入っているかを、変わったときにアプリへ知らせる"""
        in_world = bool(self.linked and self.state and self.state.get('connected'))
        shown = (self.linked, in_world, '' if self.linked else self.reason)
        if shown == self._shown or self.notify is None:
            return
        self._shown = shown
        self.notify({'v': VERSION, 'type': 'game.state', 'linked': shown[0], 'in_world': shown[1], 'reason': shown[2]})

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
                if self.reason != 'busy':
                    self.reason = 'off' if self._closed else 'connecting'
                for f in self._pending.values():
                    if not f.done():
                        f.set_result({'status': 'unavailable'})
                self._pending.clear()
                for id_ in list(self._cards):   # 終わりを聞けなくなった技の付箋
                    self._close_card({'id': id_, 'ok': False, 'reason': 'unlinked'})
                self.publish()
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
            self.linked, self.owner, self.state, self.reason = True, m.get('owner'), m.get('state'), ''
            log.info('マイクラの体とつながった')
            debug_log.record('minecraft', what='linked')
            self.publish()
        elif kind == 'busy':
            log.info('マイクラの体は、ほかの会話が使っている')
            self.reason = 'busy'
            self.publish()
        elif kind == 'state':
            self.state = m
            self.publish()
        elif kind in ('started', 'error', 'seen'):
            f = self._pending.pop(m.get('id'), None)
            if f is not None and not f.done():
                f.set_result({'status': 'started'} if kind == 'started' else
                             {'status': 'seen', 'message': m} if kind == 'seen' else
                             refused(m))
        elif kind == 'done':
            self.on_done(m)
        elif kind == 'event':
            self.on_event(m)

    # ---- 頼む（道具 tools/minecraft.py から） ----

    async def do(self, skill: str, args: dict | None = None) -> dict:
        """技を頼む。始めたか（started）を返す。終わったら、知らせで話す（on_done）"""
        if not self.linked or self._ws is None:
            return {'status': 'unavailable'}
        args = args or {}
        name = title(skill, args)
        if self.board is not None and any(c.title == name for c in self._cards.values() if c.status == tasks.RUNNING):
            return {'status': 'already_doing'}   # 同じ頼みは、もうしている
        id_ = next(self._ids)
        f = asyncio.get_running_loop().create_future()
        self._pending[id_] = f
        self._asked[id_] = name
        await self._send({'type': 'do', 'id': id_, 'skill': skill, 'args': args})
        try:
            result = await asyncio.wait_for(f, START_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(id_, None)
            return {'status': 'no_answer'}
        if result.get('status') == 'started' and self.board is not None:
            self._cards[id_] = self.board.add('game', name, tasks.RUNNING, 'ciel', ref=str(id_))
        return result

    async def look(self) -> dict:
        """今の景色を 1 枚撮ってもらい、目の係に渡す。道具の返事の続きで、心がその絵を見る"""
        if not self.linked or self._ws is None or self.eyes is None:
            return {'status': 'unavailable'}
        id_ = next(self._ids)
        f = asyncio.get_running_loop().create_future()
        self._pending[id_] = f
        await self._send({'type': 'look', 'id': id_})
        try:
            result = await asyncio.wait_for(f, LOOK_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(id_, None)
            return {'status': 'no_answer'}
        if result.get('status') != 'seen':
            return result
        m = result['message']
        try:
            jpeg = base64.b64decode(m.get('jpeg') or '', validate=True)
        except (binascii.Error, ValueError):
            return {'status': 'error', 'reason': 'bad_image'}
        facing = FACING.get(m.get('facing') or '')
        pic = self.eyes.see_minecraft(jpeg, f'{facing}を向いている' if facing else '')
        if pic is None:
            return {'status': 'error', 'reason': 'bad_image'}
        return {'status': 'seen', 'view': pic.id, 'facing': facing}

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
        foot = s.get('footing') or {}
        if foot.get('height'):
            lines.append(f"足元：{foot.get('on')}（木の上。地面から約 {foot['height']} ブロック。ふつうに歩いては降りられない）")
        elif foot.get('on'):
            lines.append(f"足元：{foot['on']}")
        blocks = sorted((s.get('blocks') or {}).items(), key=lambda kv: -kv[1])[:BLOCKS_SHOWN]
        if blocks:
            lines.append('近くのブロック：' + '、'.join(f'{k}×{n}' for k, n in blocks))
        if self.owner and not any(p['name'] == self.owner for p in s.get('players') or []):
            lines.append(f'{self.owner}（持ち主）は近くにいない')
        return '\n'.join(lines)

    # ---- 出来事を選んで話す（docs/minecraft-design-ja.md の 5 章） ----

    def on_done(self, m: dict) -> None:
        """技の終わり（体からの返事）。うまくいかなかったら、理由・途中までの成果・同じ頼みの何回目かを心へ知らせ、
        呼び直すか、困っていることを伝えて相談するかを心が決める（config/prompts/minecraft.md）。
        「途中でうまくいかなくなった」だけでは、心は呼び直しも相談もせず「少し止まってしまっていた」と言った（2026-11-05）"""
        name = self._asked.pop(m.get('id'), None) or '頼まれた技'
        self._close_card(m)
        note = m.get('note') or {}
        got = '、'.join(f'{k}×{n}' for k, n in (note.get('gained') or {}).items())
        if note.get('descended'):
            got = '、'.join(x for x in (got, f"{note['descended']} ブロック降りた") if x)
        reason = m.get('reason') or 'error'
        if m.get('ok') and not note.get('short'):
            self._fails.pop(name, None)
            if got:   # 集め終えた。そばへ行く・場所へ行くは、着いたのが見えるので言わない
                self._tell('done', f'[マイクラ：頼まれた「{name}」ができた（{got}）]', SETTLE, limit=False)
            return
        if not m.get('ok') and (reason in QUIET_REASONS or reason == 'died'):   # 倒れたことは died の出来事で言う
            return
        why = reasons(note.get('short') or reason, note)
        if reason == 'error' and m.get('detail'):
            why += f"（体のエラー：{m['detail']}）"
        times = self._fails[name] = self._fails.get(name, 0) + 1
        if m.get('ok'):   # 頼まれた数に届かなかった
            line = (f'[マイクラ：頼まれた「{name}」は途中まで（できたところ：{got}）。残りの理由：{why}。'
                    f'同じ頼みでうまくいかなかったのは {times} 回目]')
        else:
            line = (f'[マイクラ：頼まれた「{name}」ができなかった。理由：{why}。できたところ：{got or "なし"}。'
                    f'同じ頼みでうまくいかなかったのは {times} 回目]')
        self._tell('failed', line, SETTLE, limit=False)

    def _close_card(self, m: dict) -> None:
        card = self._cards.pop(m.get('id'), None)
        if card is None or self.board is None:
            return
        reason = m.get('reason')
        if m.get('ok') or reason in ('stopped', 'replaced'):
            note = {'stopped': 'やめた', 'replaced': 'ほかの頼みに替えた'}.get(reason, '')
            if m.get('ok') and (m.get('note') or {}).get('short'):
                note = '途中まで'
            self.board.move(card, tasks.DONE, note=note or None)
        else:
            self.board.move(card, tasks.FAILED, note=WHY_FAILED.get(reason, WHY_FAILED['error']).split('（')[0])

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
        elif kind == 'on_tree':
            self._tell(kind, f"[マイクラ：木の上にいる（足元：{m.get('on')}、地面から約 {m.get('height')} ブロック）。"
                             'ふつうに歩いては降りられない]', SETTLE)
        elif kind == 'defeated':
            self._remember(f"マイクラで {m.get('name')} を倒した")
            self._tell(kind, f"[マイクラ：{m.get('name')}を倒した]", SETTLE)
        elif kind in ('spawned', 'disconnected'):
            debug_log.record('minecraft', what=kind)
        # 夜・天気・プレイヤーの出入り・チャットは様子に入るだけ（チャットは B4）

    def _tell(self, kind: str, line: str, settle: float, *, limit: bool = True) -> None:
        """知らせは、話の切れ目を待つあいだに届いた分をまとめて 1 回で言う（mouth.say_latest の merge）。
        今の様子は、心と小脳へいつも「[マイクラの様子]」で渡るので、知らせには入れない"""
        now = time.monotonic()
        if limit and now - self._said.get(kind, -SAME_KIND_SECONDS) < SAME_KIND_SECONDS:
            return
        self._said[kind] = now
        debug_log.record('minecraft', what=kind)
        self.say('game', settle=settle, instructions=line, merge=True)

    def _remember(self, text: str) -> None:
        if self.diary is not None and text not in self._remembered:
            self._remembered.add(text)
            try:
                self.diary.add('minecraft', text)
            except Exception as e:
                log.info('日記に書けない：%s', type(e).__name__)
