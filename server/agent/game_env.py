# -*- coding: utf-8 -*-
"""ゲームの環境（MCP）へつなぐ係。docs/games/game-environment-mcp-design-ja.md の 5 章。

- 会話サーバーはゲームを知らない。ゲームは MCP のサーバー（マイクラなら server/minecraft の src/ciel/mcp.js）で、
  「シエルのゲームの決まり」（版 1）に沿って、道具・様子・遊び方の指示・出来事を出す。ここはそれを受けて、心・口・付箋・
  目的の係・アプリへ渡すだけ。ゲームの名前・技の名前・物の名前・失敗の理由の文は、ゲームの側が持つ。
- 会話の始めにつなぐ（prepare）：決まり（game://profile）・道具の一覧・遊び方の指示（prompt play）を読む。設定は会話の始めに
  読んで会話の中では変えないので、指示と道具はここで決まる。ゲームのサーバーが止まっていても、会話は続ける（道具が無いだけ）。
- つないだだけでは体を動かさない。アプリの設定「マイクラで一緒に遊ぶ」（topic ciel.game の game.link）がオンになったら、
  決まりの link_tool で体を受け持つ。体を動かせる会話は 1 つだけで、ほかの会話が使っていれば busy。
- 様子は resource game://state。変わったという知らせ（notifications/resources/updated）で読み直す。
- 出来事は MCP の知らせ notifications/message（logger 'ciel.event'）。急ぎの度合い（urgency）で口へ渡す切れ目を決め、
  発行ID・世代・時刻を検証し、共通反応基盤へ渡す。日記に残す一文は会話で同じことを重複させない。
- 時間がかかる技（_meta の ciel/long_running）は付箋にし、終わり（kind task_done）で閉じる。同じ頼み（題）が続けて
  うまくいかなかった回数は、ここで数えて知らせに添える。
- つなぐ先は環境変数 CIEL_GAMES（例 minecraft=http://127.0.0.1:8771/mcp）。今は最初の 1 つだけを使う。空ならつながない。
"""
import asyncio
import base64
import contextlib
import json
import logging
import math
import os
import re
import time
import uuid
from datetime import timedelta
from typing import Callable

from mcp import ClientSession, types as mcp_types   # 読み込みに数秒かかることがあるので、会話の始めの待ち時間の外で読む
from mcp.client.streamable_http import streamablehttp_client

import board as tasks
import debug_log
from errors import ERRORS

log = logging.getLogger('ciel-agent.game')

ENV = 'CIEL_GAMES'
TOPIC = 'ciel.game'
VERSION = 1
PROFILE_VERSION = 2
PREPARE_TIMEOUT = 4.0      # 会話の始めに、ゲームのサーバーの決まり・道具・指示を読むのを待つ上限
CALL_TIMEOUT = 40.0        # 道具 1 回の答えを待つ上限（景色を撮るのに 25 秒かかることがある）
PING_SECONDS = 20.0        # 受け持ち前・待機中も通信を保つ（体の側は 60 秒無通信でセッションを閉じる）
LINK_RETRY_SECONDS = 3.0   # 使用中・接続待ちからの再試行。ほかの会話の所有権は奪わない
RETRY_MIN, RETRY_MAX = 3.0, 30.0
URGENT_SETTLE = 0.3        # 危ない知らせは、すぐの切れ目で言う
SETTLE = 1.2               # ふつうの知らせは、相手がこの秒数だまってから言う
SHOWN_ROLES = ('act', 'look', 'know')   # 心に渡す道具の役目（link・goal は会話サーバーが使う）


def parse(text: str) -> dict[str, str]:
    """「minecraft=http://…, other=http://…」→ {ゲーム: つなぐ先}"""
    games = {}
    for part in (text or '').split(','):
        name, _, url = part.strip().partition('=')
        name, url = name.strip().lower(), url.strip()
        if name and url.startswith(('http://', 'https://')):
            games[name] = url
    return games


GAMES = parse(os.environ.get(ENV, ''))


def from_env() -> 'GameEnv | None':
    if not GAMES:
        return None
    game, url = next(iter(GAMES.items()))
    if len(GAMES) > 1:
        log.warning('ゲームは今は 1 つだけつなぐ（%s）。ほかは使わない', game)
    return GameEnv(game, url)


def _text(result) -> str:
    return '\n'.join(getattr(c, 'text', '') for c in getattr(result, 'content', None) or [] if getattr(c, 'type', '') == 'text')


def _json(text: str) -> dict:
    try:
        v = json.loads(text)
    except (TypeError, ValueError):
        return {'status': 'ok', 'text': text} if text else {'status': 'error'}
    return v if isinstance(v, dict) else {'status': 'ok', 'value': v}


def _link_wanted(packet) -> tuple[str | None, bool] | None:
    """アプリのスイッチ：(ゲーム, オンか)。env.link {game, on}。以前のアプリの game.link {on} は、ゲームを言わない（None）"""
    if getattr(packet, 'topic', None) != TOPIC:
        return None
    try:
        m = json.loads(packet.data.decode('utf-8'))
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    if not isinstance(m, dict):
        return None
    if m.get('type') == 'env.link' and isinstance(m.get('game'), str):
        return m['game'], bool(m.get('on'))
    return (None, bool(m.get('on'))) if m.get('type') == 'game.link' else None


def listing(env: 'GameEnv | None') -> dict:
    """アプリへ：つなげるゲームの一覧（env.list）。アプリは、ここの名前でスイッチを出す（アプリはゲームの名前を持たない）"""
    games = [{'game': env.game, 'label': env.label}] if env is not None and env.profile else []
    return {'v': VERSION, 'type': 'env.list', 'games': games}


def refuse(notify: Callable[[dict], None]) -> Callable:
    """つなぐ先の無い会話サーバー：アプリがオンにしたら、つなげないと返す"""
    def on_data(packet) -> None:
        wanted = _link_wanted(packet)
        if wanted and wanted[1]:
            if wanted[0] is not None:
                notify({'v': VERSION, 'type': 'env.state', 'game': wanted[0], 'label': '', 'linked': False, 'playing': False,
                        'reason': 'unavailable'})
            notify({'v': VERSION, 'type': 'game.state', 'linked': False, 'in_world': False, 'reason': 'unavailable'})
    return on_data


class GameEnv:
    def __init__(self, game: str, url: str, *, connect=None) -> None:
        self.game = game
        self.url = url
        self._connect = connect or GameEnv._connect_http   # (env) → ClientSession の文脈。試験では手元の MCP のサーバーへつなぐ
        self.say: Callable[..., None] | None = None     # mouth.Mouth.say_latest（why, settle=, instructions=, merge=）
        self.diary = None            # diary.Diary（倒した・倒れたなど、本当にあったことを残す）
        self.board = None            # board.Board（頼まれた技を付箋にする）
        self.notify: Callable[[dict], None] | None = None   # アプリへの知らせ（game.state）
        self.eyes = None             # eyes.Eyes（撮った景色を渡す先）
        self.goals = None            # goals.GoalRunner（係が体を使っているあいだは、心の体の道具を断る）
        self.profile: dict = {}
        self.label = game
        self.instructions = ''       # ゲームの遊び方の指示（prompt play）
        self.tools: list = []        # 心に渡す道具（LiveKit の道具に包んだもの）
        self.meta: dict[str, dict] = {}   # 道具の名前 → _meta
        self.titles: dict[str, str] = {}  # 道具の名前 → 見せる名前（MCP の title。アプリの「いま」）
        self.activity = None              # activity.Activity（いまのシエル。体の技の始まりと終わり）
        self.route_words: re.Pattern | None = None
        self.state: dict = {}
        self.linked = False          # 体を受け持っている
        self.wanted = False          # アプリの設定でオン
        self.reason = 'off'          # 受け持っていない理由（off・connecting・busy・unavailable）
        self._session = None
        self._ready: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._closed = False
        self._shown: tuple | None = None
        self._cards: dict = {}       # 技の id → 付箋
        self._completed: dict = {}   # 終了の先着・重複を記録。接続の世代もキーに含める
        self._body: dict = {}
        self._body_protocol_valid = False
        self._observed: set = set()
        self._connection_epoch = 0
        self._act_lock = asyncio.Lock()
        self._link_lock = asyncio.Lock()
        self._fails: dict[str, int] = {}
        self._input_epoch = None
        self._input_seq = -1
        self._input_ids = set()
        self._remembered: set[str] = set()
        self._stop_event: asyncio.Event | None = None

    # ---- つなぐ ----

    @contextlib.asynccontextmanager
    async def _connect_http(self):
        async with streamablehttp_client(self.url, timeout=10) as (read, write, _):
            bound = [None]
            async def log_current(params):
                if bound[0] is not None and self._session is bound[0]:
                    await self._on_log(params)
            async def message_current(message):
                if bound[0] is not None and self._session is bound[0]:
                    await self._on_message(message)
            async with ClientSession(read, write, logging_callback=log_current, message_handler=message_current) as s:
                bound[0] = s
                try:
                    yield s
                finally:
                    bound[0] = None

    async def prepare(self) -> bool:
        """会話の始め：つないで、決まり・道具・指示を読む。読めなければ False（道具も指示も無し）"""
        self._ready = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._ready.wait(), PREPARE_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning('ゲーム（%s）の環境につなげない：このゲームの道具は無しで続ける', self.game)
            return False
        return self._session is not None and bool(self.profile)

    async def _run(self) -> None:
        retry = RETRY_MIN
        first = True
        while not self._closed:
            try:
                async with self._connect(self) as session:
                    await session.initialize()
                    if first:
                        await self._read_setup(session)
                        first = False
                    self._session = session
                    self._stop_event = asyncio.Event()
                    self._connection_epoch += 1
                    retry = RETRY_MIN
                    log.info('ゲーム（%s）の環境とつながった', self.game)
                    if self._ready is not None:
                        self._ready.set()
                    if self.wanted:   # つなぎ直した：アプリがオンのままなら、もう一度受け持つ
                        await self._link(True)
                    await self._closing()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info('ゲーム（%s）の環境につなげない：%s', self.game, type(e).__name__)
            finally:
                self._connection_epoch += 1
                self._session = None
                if self.linked:
                    log.info('ゲーム（%s）の体から切れた', self.game)
                self.linked = False
                for key, card in list(self._cards.items()):   # 終わりを聞けなくなった技の付箋
                    self._close_card_of(card, 'failed', '体から切れた')
                    if self.activity is not None:
                        self.activity.task_done(f'{self.game}:{key}', '', False, quiet=True)
                self._cards.clear()
                self._body = {}
                self._body_protocol_valid = False
                self._observed.clear()
                if self.activity is not None:
                    self.activity.set_body({'version': 1, 'phase': 'unknown', 'reason': 'disconnected'})
                if self.reason not in ('busy',):
                    self.reason = 'off' if not self.wanted else 'connecting'
                self.publish()
            if self._closed:
                return
            await asyncio.sleep(retry)
            retry = min(retry * 2, RETRY_MAX)

    async def _closing(self) -> None:
        """受け持ちの有無にかかわらず通信を保ち、切れた通信は作り直す。"""
        session = self._session
        loop = asyncio.get_running_loop()
        next_ping = loop.time() + PING_SECONDS
        while not self._closed and not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), LINK_RETRY_SECONDS)
                return
            except asyncio.TimeoutError:
                pass
            if loop.time() >= next_ping:
                try:
                    await asyncio.wait_for(session.send_ping(), 10)
                except Exception as e:
                    log.info('ゲーム（%s）の通信をつなぎ直す：%s', self.game, type(e).__name__)
                    self._reconnect(session)
                    return
                next_ping = loop.time() + PING_SECONDS
            if self.wanted and not self.linked:
                await self._link(True)

    def _reconnect(self, session) -> None:
        if session is not self._session or self._closed:
            return
        self.linked = False
        self.reason = 'connecting' if self.wanted else 'off'
        self._connection_epoch += 1
        if self._stop_event is not None:
            self._stop_event.set()
        if self.activity is not None:
            self.activity.set_body({'version': 1, 'phase': 'unknown', 'reason': self.reason})
        self.publish()

    async def _read_setup(self, session) -> None:
        r = await session.read_resource('game://profile')
        profile = _json(getattr(r.contents[0], 'text', '') if r.contents else '')
        if profile.get('profile') != PROFILE_VERSION:
            raise RuntimeError(f'知らない決まりの版：{profile.get("profile")}')
        self.profile = profile
        self.label = profile.get('label') or self.game
        words = profile.get('route_words')
        try:
            self.route_words = re.compile(words) if words else None
        except re.error:
            log.warning('ゲーム（%s）の頼みの言葉を読めない', self.game)
        try:
            p = await session.get_prompt('play')
            self.instructions = '\n'.join(getattr(m.content, 'text', '') for m in p.messages).strip()
        except Exception as e:
            log.info('ゲーム（%s）の遊び方の指示が無い：%s', self.game, type(e).__name__)
        listed = await session.list_tools()
        self.tools, self.meta = [], {}
        prefix = self.game + '_'
        for t in listed.tools:
            if not t.name.startswith(prefix):   # ほかのゲームの道具とぶつからないよう、ゲームの名前で始まるものだけ
                log.warning('ゲーム（%s）の道具の名前が決まりと違うので使わない：%s', self.game, t.name)
                continue
            meta = dict(t.meta or {})
            self.meta[t.name] = meta
            if getattr(t, 'title', None):
                self.titles[t.name] = t.title
            if meta.get('ciel/role') in SHOWN_ROLES:
                self.tools.append(self._wrap(t.name, t.description or '', t.inputSchema or {'type': 'object', 'properties': {}}))
        log.info('ゲーム（%s）の道具 %d 個', self.game, len(self.tools))

    def on_data(self, packet) -> None:
        """アプリの設定「（ゲーム）で一緒に遊ぶ」（env.link、以前のアプリは game.link）。オンで体を受け持ち、オフで離す
        （体はその場で待つ）"""
        wanted = _link_wanted(packet)
        if wanted is None or wanted[0] not in (None, self.game):
            return
        on = wanted[1]
        self.wanted = on
        if self._session is None:
            self.reason = 'connecting' if on else 'off'
            self.publish()
            return
        asyncio.create_task(self._link(on))

    async def _link(self, on: bool) -> None:
        async with self._link_lock:
            if self._closed or on != self.wanted or self._session is None:
                return
            await self._link_once(on)

    async def _link_once(self, on: bool) -> None:
        session = self._session
        was_busy = self.reason == 'busy'
        if on and self.reason != 'busy':
            self.reason = 'connecting'
            self.publish()
        r = await self._call(self.profile.get('link_tool') or f'{self.game}_link', {'on': on})
        if session is not self._session or (self._stop_event is not None and self._stop_event.is_set()):
            return
        if on and (not self.wanted or self._closed):
            # 接続要求の返事を待つ間にオフになった。取れた体を残さない。
            await self._call(self.profile.get('link_tool') or f'{self.game}_link', {'on': False})
            r = {'status': 'off'}
        status = r.get('status')
        if status in ('no_answer', 'unavailable', 'error'):
            self._reconnect(session)
            return
        if status == 'linked':
            await self._refresh()   # 様子を読んでから、受け持ったことにする
            if session is not self._session or (self._stop_event is not None and self._stop_event.is_set()):
                return
        self.linked = status == 'linked'
        self.reason = '' if self.linked else ('busy' if status == 'busy' else 'off' if not on else 'connecting')
        if self.linked:
            log.info('ゲーム（%s）の体を受け持った', self.game)
            debug_log.record('game', game=self.game, what='linked')
        else:
            if status == 'busy' and not was_busy:
                log.info('ゲーム（%s）の体は、ほかの会話が使っている', self.game)
            if self.activity is not None:
                self.activity.set_body({'version': 1, 'phase': 'unknown', 'reason': self.reason})
        self.publish()

    async def close(self) -> None:
        self._closed = True
        self.wanted = False
        if self._session is not None and self.linked:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._call(self.profile.get('link_tool') or f'{self.game}_link', {'on': False}), 3)
        stop = getattr(self, '_stop_event', None)
        if stop is not None:
            stop.set()
        if self._task is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._task, 3)
            if not self._task.done():
                self._task.cancel()
            self._task = None
        self.reason = 'off'
        self.publish()

    def publish(self) -> None:
        if not self.linked:
            self._input_epoch, self._input_seq = None, -1
            self._input_ids.clear()
        """体を受け持ったか・ゲームに入っているかを、変わったときにアプリへ知らせる"""
        shown = (self.linked, self.playing(), '' if self.linked else self.reason)
        if shown == self._shown or self.notify is None:
            return
        self._shown = shown
        self.notify({'v': VERSION, 'type': 'env.state', 'game': self.game, 'label': self.label, 'linked': shown[0],
                     'playing': shown[1], 'reason': shown[2]})
        # 以前のアプリ（env.state を読まない）のため。E6 で消す
        self.notify({'v': VERSION, 'type': 'game.state', 'linked': shown[0], 'in_world': shown[1], 'reason': shown[2]})

    # ---- 道具 ----

    async def _call(self, name: str, args: dict, timeout: float = CALL_TIMEOUT):
        """道具を呼んで、返事の JSON（dict）を返す。絵があれば '_images' に入れる"""
        if self._session is None:
            return {'status': 'unavailable'}
        session = self._session
        call_id = uuid.uuid4().hex
        debug_log.record('game_call', id=call_id, name=name, arguments=args)
        try:
            r = await self._session.call_tool(name, args, read_timeout_seconds=timedelta(seconds=timeout))
        except Exception as e:
            debug_log.record('game_result', id=call_id, name=name, result={'status': 'no_answer', 'reason': type(e).__name__})
            log.info('ゲーム（%s）の道具 %s が答えない：%s', self.game, name, type(e).__name__)
            if (name == (self.profile.get('link_tool') or f'{self.game}_link')
                    or getattr(getattr(e, 'error', None), 'message', '') == 'Session terminated'
                    or isinstance(e, (ConnectionError, OSError))
                    or type(e).__name__ in ('ClosedResourceError', 'BrokenResourceError')):
                self._reconnect(session)
            return {'status': 'no_answer'}
        out = _json(_text(r))
        images = [c for c in r.content or [] if getattr(c, 'type', '') == 'image']
        if images:
            out['_images'] = images
        if getattr(r, 'isError', False) and 'status' not in out:
            out['status'] = 'error'
        debug_log.record('game_result', id=call_id, name=name, result={k:v for k,v in out.items() if k != '_images'})
        return out

    def _wrap(self, name: str, description: str, schema: dict):
        from livekit.agents import function_tool

        async def impl(raw_arguments: dict) -> str:
            return json.dumps(await self.use(name, raw_arguments or {}), ensure_ascii=False)
        return function_tool(impl, raw_schema={'name': name, 'description': description, 'parameters': schema})

    async def use(self, name: str, args: dict) -> dict:
        # 目的の停止と新しい命令の投入を、ほかの直接命令が追い越さない。
        if self.meta.get(name, {}).get('ciel/role') == 'act':
            async with self._act_lock:
                return await self._use(name, args)
        return await self._use(name, args)

    async def _use(self, name: str, args: dict) -> dict:
        """心が呼んだゲームの道具"""
        meta = self.meta.get(name, {})
        role = meta.get('ciel/role')
        if role in ('act', 'look') and not self.linked:
            return {'status': 'unavailable'}
        if role == 'act' and not meta.get('ciel/stops') and not self._body_protocol_valid:
            return {'status': 'error', 'reason': 'body_protocol_mismatch'}
        busy = self.goals.body_step() if self.goals is not None and role == 'act' else None
        planning = False
        spontaneous = self.activity is not None and self.activity.thinking_origin == 'initiative'
        if role == 'act' and spontaneous and (busy is not None or planning or self._body.get('current') or self._body.get('pending')):
            return {'status': 'goal_running', 'why': '依頼された体の作業を進めている'}
        if role == 'act' and busy is not None:
            if spontaneous:
                return {'status': 'goal_running', 'why': '持ち主の目的を進めている'}
            if not meta.get('ciel/stops'):
                return {'status': 'busy'}
            return await self.goals.stop()
        epoch = self._connection_epoch
        r = await self._call(name, args)
        if epoch != self._connection_epoch:
            return {'status': 'unavailable'}
        images = r.pop('_images', None)
        if images and self.eyes is not None:   # 目：景色の絵は目の係に渡し、道具の返事の続きで心が見る
            try:
                data = base64.b64decode(images[0].data, validate=True)
            except (ValueError, TypeError):
                data = b''
            pic = self.eyes.see_game(data, r.get('note') or '', self.label) if data else None
            if pic is None:
                return {'status': 'error', 'reason': 'bad_image'}
            r['view'] = pic.id
            r['note'] = f"景色の絵は「[わたしの目に見えている景色 #{pic.id}]」として、この続きで見える"
        key = self._task_key(r)
        if meta.get('ciel/long_running') and r.get('status') in ('started', 'accepted') and r.get('task') is not None:
            if key not in self._completed:
                if self.board is not None and key not in self._cards:
                    self._cards[key] = self.board.add('game', r.get('title') or name, tasks.RUNNING, 'ciel', ref=str(key))
                if self.activity is not None:
                    self.activity.task_started(f'{self.game}:{key}', r.get('title') or name)
            else:
                # 「受付／開始」が終了より遅く返ってきた。終了を正として返す。
                r = {**r, 'status': 'completed', 'ok': bool(self._completed[key].get('ok')),
                     'reason': self._completed[key].get('reason')}
        if self._body:
            self._reconcile_body()
        return r

    def tool_ids(self, *roles: str) -> frozenset[str]:
        return frozenset(n for n, m in self.meta.items() if m.get('ciel/role') in roles)

    def seeds(self) -> list[tuple[str, str | None]]:
        """振り分けの最初の例文：(文, 道具の名前)。小脳でよい発言は道具の名前が None"""
        out = [(t, n) for n, m in self.meta.items() if m.get('ciel/role') in SHOWN_ROLES for t in m.get('ciel/triggers') or []]
        out += [(t, n) for n, texts in (self.profile.get('goal_triggers') or {}).items() for t in texts]
        return out + [(t, None) for t in self.profile.get('talker_examples') or []]

    def from_comments(self) -> dict[str, bool]:
        """配信のコメントへの返事で使ってよいか（_meta の ciel/from_comments。無ければ読むだけの道具か）"""
        return {n: bool(m.get('ciel/from_comments', False)) for n, m in self.meta.items() if m.get('ciel/role') in SHOWN_ROLES}

    # ---- 様子 ----

    def playing(self) -> bool:
        """体を受け持っていて、ゲームの中にいる"""
        return bool(self.linked and self.state.get('playing'))

    async def _refresh(self) -> bool:
        if self._session is None:
            return False
        session, epoch = self._session, self._connection_epoch
        try:
            r = await self._session.read_resource('game://state')
        except Exception as e:
            log.info('ゲーム（%s）の様子を読めない：%s', self.game, type(e).__name__)
            if getattr(getattr(e, 'error', None), 'message', '') == 'Session terminated':
                self._reconnect(session)
            return False
        if session is not self._session or epoch != self._connection_epoch:
            return False
        state = _json(getattr(r.contents[0], 'text', '') if r.contents else '')
        body = state.get('body')
        self._body_protocol_valid = isinstance(body, dict) and body.get('version') == 1
        if self._body_protocol_valid:
            if (self._body.get('session'), self._body.get('epoch')) == (body.get('session'), body.get('epoch')) and body.get('revision', 0) < self._body.get('revision', -1):
                return False
            self._body = body
        else:
            self._body = {}
            if self.activity is not None:
                self.activity.set_body({'version': 1, 'phase': 'unknown', 'reason': 'body_protocol_mismatch'})
        self.state = state
        self._reconcile_body()
        self.publish()
        if self.activity is not None:
            self.activity.changed()   # 体がいましていること（いま）
        return self._body_protocol_valid

    def context(self) -> str | None:
        """心と小脳へ渡す「[マイクラの様子]」（つなぐ先が無ければ None）"""
        if not self.profile:
            return None
        head = f'[{self.label}の様子]'
        if not self.linked:
            return f'{head}\nシエルの体とつながっていない（{self.label}の中のことは分からない）'
        return f"{head}\n{self.state.get('text') or ''}".rstrip()

    def snapshot(self):
        return self.state.get('fingerprint')

    async def _on_message(self, message) -> None:
        root = getattr(message, 'root', None)
        if isinstance(root, mcp_types.ResourceUpdatedNotification) and str(root.params.uri).rstrip('/') == 'game://state':
            # 知らせを受ける係の中で答えを待つと、次の知らせ（その答え）を受けられずに詰まる。読み直しは別に走らせる
            asyncio.create_task(self._refresh())

    # ---- 出来事を話す ----

    async def _on_log(self, params) -> None:
        if getattr(params, 'logger', None) != 'ciel.event' or not isinstance(params.data, dict):
            return
        try:
            self.on_event(params.data)
        except Exception as e:
            ERRORS.report('game.event', e, kind='task')

    def on_event(self, e: dict) -> None:
        kind = e.get('kind')
        if kind == 'work_state':
            if self.goals is not None and self.goals.work:
                self.goals.accept(e.get('work'))
            return
        if kind in ('work_action', 'work_action_result'):
            debug_log.record(kind, **{k: v for k, v in e.items() if k != 'kind'})
            return
        if e.get('error'):   # 体の中のエラー（errors.py で記録・アプリへ）
            ERRORS.report(str(e['error'].get('where') or 'body'), RuntimeError(str(e['error'].get('detail') or 'error')),
                          kind='body')
        if kind == 'task_done':
            self._task_done(e)
            return
        if not self.linked:
            return
        if e.get('memorable'):
            self._remember(e['memorable'])
        urgency = e.get('urgency')
        if e.get('say') and self.activity is not None:
            self.activity.log(e['say'].strip('[]'), 'error' if urgency == 'urgent' else 'info')
        if e.get('say') and urgency in ('urgent', 'normal'):
            self._tell(kind, e['say'], URGENT_SETTLE if urgency == 'urgent' else SETTLE, event=e)

    def _task_done(self, e: dict) -> None:
        """頼まれた技の終わり。付箋を閉じ、うまくいかなかったら同じ頼みの何回目かを添えて心へ知らせる"""
        key = self._task_key(e)
        previous = self._completed.get(key)
        if previous is not None and (not previous.get('_snapshot') or e.get('_snapshot')):
            return
        self._completed[key] = e
        debug_log.record('game_task_result', id=key, ok=bool(e.get('ok')), failed=bool(e.get('failed')),
                         reason=e.get('reason'), title=e.get('title'), snapshot=bool(e.get('_snapshot')))
        if len(self._completed) > 512:
            self._completed.pop(next(iter(self._completed)))
        self._observed.discard(key)
        card = self._cards.pop(key, None)
        if self.activity is not None:
            # 止めた・替えた・切れたは「できなかった」にしない（その知らせは言わない）
            self.activity.task_done(f'{self.game}:{key}', e.get('title') or '', bool(e.get('ok')),
                                    e.get('card_note'), quiet=not e.get('ok') and not e.get('failed'))
        if card is not None:
            self._close_card_of(card, e.get('card') or ('done' if e.get('ok') else 'failed'), e.get('card_note'))
        name = e.get('title') or ''
        say = e.get('say')
        if e.get('failed'):
            times = self._fails[name] = self._fails.get(name, 0) + 1
            if say and say.endswith(']'):
                say = say[:-1] + f'。同じ頼みでうまくいかなかったのは {times} 回目]'
        elif e.get('ok'):
            self._fails.pop(name, None)
        if say:
            self._tell('task_done', say, SETTLE, event=e)

    @staticmethod
    def _task_key(event: dict):
        task = event.get('task')
        return f"{event['session']}:{task}" if event.get('session') else task

    def _reconcile_body(self) -> None:
        b = self._body
        if not b:
            return
        active = {self._task_key({'session': b.get('session'), 'task': c['id']})
                  for c in (b.get('current'), b.get('pending')) if c}
        self._observed.update(active)
        last = b.get('last') or {}
        last_key = self._task_key({'session': b.get('session'), 'task': last.get('id')})
        if last.get('id') is not None and (last_key in self._cards or last_key in self._observed):
            result = last.get('result') or {}
            self._task_done({'session': b.get('session'), 'task': last['id'], 'title': last.get('title', ''),
                             'ok': bool(result.get('ok')), 'reason': result.get('reason'), 'failed': False, '_snapshot': True})
        for key in list(self._cards):
            if key not in active and (key in self._observed or key == last_key):
                self._task_done({'task': key, 'ok': False, 'failed': False, '_snapshot': True, 'card_note': '終了を状態から確認した'})
        if self.activity is not None:
            current, pending = b.get('current') or {}, b.get('pending') or {}
            phase = current.get('phase') or ('accepted' if pending else 'idle')
            reason = current.get('reason') or ''
            if b.get('owner'):
                phase, reason = 'waiting', b['owner']
            if b.get('blocked'):
                phase, reason = 'stopping', 'stop_timeout'
            if self.state.get('playing') is False or self.state.get('linked') is False:
                phase, reason = 'unknown', 'disconnected'
            # 完了／失敗は履歴。現在の体とは区別して送る。
            self.activity.set_body({'version': 1, 'session': b.get('session', ''), 'revision': b.get('revision', 0),
                'phase': phase, 'title': current.get('title') or pending.get('title') or '',
                'next_title': pending.get('title') or '', 'reason': reason,
                'for_s': max(0, time.time() - ((b.get('owner_since') if b.get('owner') else None)
                    or current.get('since') or pending.get('since') or time.time() * 1000) / 1000),
                'last_title': last.get('title') or '', 'last_phase': last.get('phase') or '',
                'last_note': last.get('why') or '',
                'last_reason': (last.get('result') or {}).get('reason') or ''})

    def _close_card_of(self, card, how: str, note: str | None) -> None:
        if self.board is None:
            return
        self.board.move(card, tasks.DONE if how == 'done' else tasks.FAILED, note=note or None)

    def _tell(self, kind: str, line: str, settle: float, *, event: dict) -> None:
        """発行ID・時刻を検証し、所有中の体の出来事を共通反応基盤へ渡す。
        今の様子は、心と小脳へいつも様子の行で渡るので、知らせには入れない"""
        if not self.linked:
            return
        if type(event.get('input_v')) is not int or event.get('input_v') != 1 or not isinstance(event.get('event_id'), str) or not isinstance(event.get('source_epoch'), str):
            debug_log.record('reaction_rejected', source='game', reason='unsupported_game_input')
            log.warning('ゲーム（%s）の通知形式が未対応。ゲーム側MCPをinput_v 1へ更新してください', self.game)
            return
        if not 1 <= len(event['event_id']) <= 160 or not 1 <= len(event['source_epoch']) <= 160:
            return
        seq, at = event.get('seq'), event.get('occurred_at')
        if type(seq) is not int or type(at) not in (int, float) or not math.isfinite(at):
            return
        if at > time.time() + 1 or time.time() - at > (5 if kind in ('hurt', 'died', 'flee') else 30):
            return
        if self._input_epoch is not None and self._input_epoch != event['source_epoch']:
            return
        if seq <= self._input_seq or event['event_id'] in self._input_ids:
            return
        self._input_epoch, self._input_seq = event['source_epoch'], seq
        self._input_ids.add(event['event_id'])
        if len(self._input_ids) > 512:
            self._input_ids = {event['event_id']}
        debug_log.record('game', game=self.game, what=kind)
        if self.say is not None:
            self.say('game', settle=settle, instructions=line, merge=True, reaction_kind=kind, reaction_event=event)

    def _remember(self, text: str) -> None:
        if self.diary is not None and text not in self._remembered:
            self._remembered.add(text)
            try:
                self.diary.add(self.game, text)
            except Exception as e:
                log.info('日記に書けない：%s', type(e).__name__)
