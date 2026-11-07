# -*- coding: utf-8 -*-
"""ゲームの環境（MCP）へつなぐ係。docs/game-environment-mcp-design-ja.md の 5 章。

- 会話サーバーはゲームを知らない。ゲームは MCP のサーバー（マイクラなら server/minecraft の src/ciel/mcp.js）で、
  「シエルのゲームの決まり」（版 1）に沿って、道具・様子・遊び方の指示・出来事を出す。ここはそれを受けて、心・口・付箋・
  目的の係・アプリへ渡すだけ。ゲームの名前・技の名前・物の名前・失敗の理由の文は、ゲームの側が持つ。
- 会話の始めにつなぐ（prepare）：決まり（game://profile）・道具の一覧・遊び方の指示（prompt play）を読む。設定は会話の始めに
  読んで会話の中では変えないので、指示と道具はここで決まる。ゲームのサーバーが止まっていても、会話は続ける（道具が無いだけ）。
- つないだだけでは体を動かさない。アプリの設定「マイクラで一緒に遊ぶ」（topic ciel.game の game.link）がオンになったら、
  決まりの link_tool で体を受け持つ。体を動かせる会話は 1 つだけで、ほかの会話が使っていれば busy。
- 様子は resource game://state。変わったという知らせ（notifications/resources/updated）で読み直す。
- 出来事は MCP の知らせ notifications/message（logger 'ciel.event'）。急ぎの度合い（urgency）で口へ渡す切れ目を決め、
  同じ種類（key）は SAME_KIND_SECONDS に 1 回まで。日記に残す一文（memorable）は、1 回の会話で同じことは 1 度だけ。
- 時間がかかる技（_meta の ciel/long_running）は付箋にし、終わり（kind task_done）で閉じる。同じ頼み（題）が続けて
  うまくいかなかった回数は、ここで数えて知らせに添える。
- つなぐ先は環境変数 CIEL_GAMES（例 minecraft=http://127.0.0.1:8771/mcp）。今は最初の 1 つだけを使う。空ならつながない。
"""
import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import time
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
PROFILE_VERSION = 1
PREPARE_TIMEOUT = 4.0      # 会話の始めに、ゲームのサーバーの決まり・道具・指示を読むのを待つ上限
CALL_TIMEOUT = 40.0        # 道具 1 回の答えを待つ上限（景色を撮るのに 25 秒かかることがある）
STEP_TIMEOUT = 960.0       # 目的の段（技 1 つ）が終わるまで待つ上限（体の側は 900 秒で止める）
PING_SECONDS = 20.0        # 体を受け持っているあいだ、離れていないことを知らせる間（体の側は 60 秒で離れたことにする）
RETRY_MIN, RETRY_MAX = 3.0, 30.0
SAME_KIND_SECONDS = 30.0   # 同じ種類の知らせは、この秒数に 1 回まで
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
        self._fails: dict[str, int] = {}
        self._said: dict[str, float] = {}
        self._remembered: set[str] = set()
        self._ping: asyncio.Task | None = None

    # ---- つなぐ ----

    @contextlib.asynccontextmanager
    async def _connect_http(self):
        async with streamablehttp_client(self.url, timeout=10) as (read, write, _):
            async with ClientSession(read, write, logging_callback=self._on_log, message_handler=self._on_message) as s:
                yield s

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
                self._session = None
                if self.linked:
                    log.info('ゲーム（%s）の体から切れた', self.game)
                self.linked = False
                self._stop_ping()
                for card in list(self._cards.values()):   # 終わりを聞けなくなった技の付箋
                    self._close_card_of(card, 'failed', '体から切れた')
                self._cards.clear()
                if self.reason not in ('busy',):
                    self.reason = 'off' if not self.wanted else 'connecting'
                self.publish()
            if self._closed:
                return
            await asyncio.sleep(retry)
            retry = min(retry * 2, RETRY_MAX)

    async def _closing(self) -> None:
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

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
        if on:
            self.reason = 'connecting'
            self.publish()
        r = await self._call(self.profile.get('link_tool') or f'{self.game}_link', {'on': on})
        status = r.get('status')
        if status == 'linked':
            await self._refresh()   # 様子を読んでから、受け持ったことにする
        self.linked = status == 'linked'
        self.reason = '' if self.linked else ('busy' if status == 'busy' else 'off' if not on else 'connecting')
        if self.linked:
            log.info('ゲーム（%s）の体を受け持った', self.game)
            debug_log.record('game', game=self.game, what='linked')
            self._start_ping()
        else:
            if status == 'busy':
                log.info('ゲーム（%s）の体は、ほかの会話が使っている', self.game)
            self._stop_ping()
        self.publish()

    def _start_ping(self) -> None:
        self._stop_ping()

        async def ping():
            while self._session is not None and self.linked:
                await asyncio.sleep(PING_SECONDS)
                with contextlib.suppress(Exception):
                    await self._session.send_ping()
        self._ping = asyncio.create_task(ping())

    def _stop_ping(self) -> None:
        if self._ping is not None:
            self._ping.cancel()
            self._ping = None

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
        try:
            r = await self._session.call_tool(name, args, read_timeout_seconds=timedelta(seconds=timeout))
        except Exception as e:
            log.info('ゲーム（%s）の道具 %s が答えない：%s', self.game, name, type(e).__name__)
            return {'status': 'no_answer'}
        out = _json(_text(r))
        images = [c for c in r.content or [] if getattr(c, 'type', '') == 'image']
        if images:
            out['_images'] = images
        if getattr(r, 'isError', False) and 'status' not in out:
            out['status'] = 'error'
        return out

    def _wrap(self, name: str, description: str, schema: dict):
        from livekit.agents import function_tool

        async def impl(raw_arguments: dict) -> str:
            return json.dumps(await self.use(name, raw_arguments or {}), ensure_ascii=False)
        return function_tool(impl, raw_schema={'name': name, 'description': description, 'parameters': schema})

    async def use(self, name: str, args: dict) -> dict:
        """心が呼んだゲームの道具"""
        meta = self.meta.get(name, {})
        role = meta.get('ciel/role')
        if role in ('act', 'look') and not self.linked:
            return {'status': 'unavailable'}
        busy = self.goals.body_step() if self.goals is not None and role == 'act' and not meta.get('ciel/stops') else None
        if busy is not None:
            # 係が体で段を進めている：体は一度に 1 つの技なので、ここで動かすと係の技が替わって目的が止まる（2026-11-07）
            return {'status': 'goal_running', 'why': f'目的の係が「{busy}」を体で進めている',
                    'next': '待てば係が続ける。先にこちらをしたいなら stop_goal で目的を止めてから'}
        r = await self._call(name, args)
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
        if meta.get('ciel/long_running') and r.get('status') == 'started' and self.board is not None and r.get('task') is not None:
            self._cards[r['task']] = self.board.add('game', r.get('title') or name, tasks.RUNNING, 'ciel', ref=str(r['task']))
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

    async def _refresh(self) -> None:
        if self._session is None:
            return
        try:
            r = await self._session.read_resource('game://state')
        except Exception as e:
            log.info('ゲーム（%s）の様子を読めない：%s', self.game, type(e).__name__)
            return
        self.state = _json(getattr(r.contents[0], 'text', '') if r.contents else '')
        self.publish()

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
        if e.get('error'):   # 体の中のエラー（errors.py で記録・アプリへ）
            ERRORS.report(str(e['error'].get('where') or 'body'), RuntimeError(str(e['error'].get('detail') or 'error')),
                          kind='body')
        if kind == 'task_done':
            self._task_done(e)
            return
        if e.get('memorable'):
            self._remember(e['memorable'])
        urgency = e.get('urgency')
        if e.get('say') and urgency in ('urgent', 'normal'):
            self._tell(kind, e['say'], URGENT_SETTLE if urgency == 'urgent' else SETTLE, key=e.get('key'))

    def _task_done(self, e: dict) -> None:
        """頼まれた技の終わり。付箋を閉じ、うまくいかなかったら同じ頼みの何回目かを添えて心へ知らせる"""
        card = self._cards.pop(e.get('task'), None)
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
            self._tell('task_done', say, SETTLE, key=None)

    def _close_card_of(self, card, how: str, note: str | None) -> None:
        if self.board is None:
            return
        self.board.move(card, tasks.DONE if how == 'done' else tasks.FAILED, note=note or None)

    def _tell(self, kind: str, line: str, settle: float, *, key: str | None) -> None:
        """知らせは、話の切れ目を待つあいだに届いた分をまとめて 1 回で言う（mouth.say_latest の merge）。
        今の様子は、心と小脳へいつも様子の行で渡るので、知らせには入れない"""
        now = time.monotonic()
        if key is not None:
            if now - self._said.get(key, -SAME_KIND_SECONDS) < SAME_KIND_SECONDS:
                return
            self._said[key] = now
        debug_log.record('game', game=self.game, what=kind)
        if self.say is not None:
            self.say('game', settle=settle, instructions=line, merge=True)

    def _remember(self, text: str) -> None:
        if self.diary is not None and text not in self._remembered:
            self._remembered.add(text)
            try:
                self.diary.add(self.game, text)
            except Exception as e:
                log.info('日記に書けない：%s', type(e).__name__)


class GoalsAdapter:
    """目的の係（goals.py）のゲームの係を、ゲームの MCP の道具（決まりの goals）で動かす。段の中身はゲームが持つ"""

    def __init__(self, env: GameEnv) -> None:
        self.env = env

    def _tool(self, key: str) -> str | None:
        return (self.env.profile.get('goals') or {}).get(key)

    def available(self) -> bool:
        return bool(self.env.linked and self._tool('plan'))

    @staticmethod
    def _step_dict(s) -> dict:
        return {'kind': s.kind, 'args': s.args, 'label': s.label, 'progress': s.progress}

    async def plan(self, goal):
        r = await self.env._call(self._tool('plan'), {'spec': goal.spec or {}})
        if r.get('error') or r.get('status') in ('unavailable', 'no_answer', 'busy', 'error'):
            return {'error': r.get('error') or r.get('status'), 'why': r.get('why')}
        return r.get('steps')   # None：係では分けられない目的（心が進める）

    async def run(self, goal, step) -> dict:
        return await self.env._call(self._tool('step'), {'step': self._step_dict(step)}, timeout=STEP_TIMEOUT)

    def check(self, goal, step, result) -> tuple[bool, list | None]:
        result = result or {}
        progress = result.get('progress', step.progress)
        return bool(result.get('complete', result.get('ok'))), progress

    async def repair(self, goal, step, result):
        remaining = [self._step_dict(s) for s in goal.steps if s.status != 'done']
        r = await self.env._call(self._tool('repair'), {'spec': goal.spec or {}, 'step': self._step_dict(step),
                                                         'result': result or {}, 'remaining': remaining})
        if not r.get('steps'):
            return None
        return r['steps'], r.get('text') or '計画を直した'

    def snapshot(self):
        return self.env.snapshot()

    def why(self, reason: str, result: dict | None = None) -> str:
        return ((result or {}).get('why_short') or (self.env.profile.get('reasons') or {}).get(reason)
                or (self.env.profile.get('reasons') or {}).get('error') or 'うまくいかなかった')

    async def stop(self) -> None:
        tool = self.env.profile.get('stop_tool')
        if tool:
            await self.env._call(tool, {})
