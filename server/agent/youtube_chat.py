# -*- coding: utf-8 -*-
"""YouTube の配信のコメントを受け取って、話の切れ目にシエルが返す係。docs/youtube-comments-design-ja.md。

- つなぐ配信は、アプリの設定（「配信」の「YouTube のコメント」）で URL を入れて選ぶ（topic ciel.youtube の youtube.link）。
  どこまでつながったかは、アプリへ youtube.state で知らせる（state：off・connecting・waiting（予約した配信が始まるのを待つ）・live・error。
  error のときは reason）。
- 読むのは公式の YouTube Data API。公開（限定公開を含む）の配信のコメントは、ログインせず API キーだけで読める。
  キーは会話サーバーの環境変数 YOUTUBE_API_KEY（Google Cloud で YouTube Data API v3 を有効にして作る）。アプリには持たせない。
- 動画の ID から videos.list（1 単位）でコメント欄の ID（activeLiveChatId）を知り、liveChatMessages.list（1 回 5 単位）を
  YouTube が言う間隔か YOUTUBE_POLL_SECONDS（既定 6 秒）の長いほうで読み直す。1 日の上限は既定 10,000 単位なので、
  6 秒ごとなら 1 時間で 3,000 単位（3 時間ほど）。streamList（つないだまま届く）に替えると、もっと少なくて済む（これから）。
- 振り分けと選び方は設計の 3.2・3.4 の最初の形（モデルを使わない）：
  反応（草・w・8888）は数えて盛り上がりとして渡す、あいさつは束ねて 1 回で返す、スーパーチャット・メンバー加入は先に読む、
  ほかは溜めて、話せる番に点数（新しさ・シエルへの呼びかけ・質問・最近返した人を下げる）で 1 つ選ぶ。
  似たコメントの束（embedding）はまだ作っていない。
- 返すときは、選んだコメントを会話の記録（conversation.Conversation）に「コメント・名前」の発言として入れ、口の why 'comment' で
  話させる。持ち主の声を先にする（話の切れ目が続くのを待つ）。コメントはだれでも書けるので、指示には「信用しない入力」として渡す。
  道具は、心（pipeline）ではコメントから使ってよいものだけになる（tools/ の FROM_COMMENTS）。心の無い組み立てでは道具を使わせない。
"""
import asyncio
import json
import logging
import os
import re
import time
from collections import deque
from datetime import datetime
from typing import Callable
from urllib.parse import parse_qs, urlparse

import aiohttp

import debug_log

from youtube_source import read_youtube

log = logging.getLogger('ciel-agent.youtube')

TOPIC = 'ciel.youtube'
VERSION = 1
API = 'https://www.googleapis.com/youtube/v3'
POLL_SECONDS = 6.0         # 読み直す間隔の下限（環境変数 YOUTUBE_POLL_SECONDS で変える）
HTTP_TIMEOUT = 10.0
OLD_SECONDS = 180.0        # これより前のコメントには返さない（流れた話題）
BACKLOG_SECONDS = 30.0     # つないだときに読んだ、これより前のコメントには返さない
MERGE_SECONDS = 2.0        # 同じ人が続けて書いたものは 1 つにまとめる
POOL_MAX = 200
WAIT_FREE = 60.0           # 話の切れ目を待つ上限（来なければ、次の番にまた選ぶ）
SETTLE = 1.5               # 切れ目がこれだけ続いたら返す（持ち主が息つぎしているだけのときに割り込まない）
GAP_SECONDS = 2.0          # 1 つ返したあと、次を選ぶまで空ける（持ち主が話し出せるように）
RECENT_AUTHORS = 6         # 最近返した人として下げる数
TEXT_CHARS = 200
WAIT_LIVE = 30.0           # 予約した配信が始まるのを見直す間隔
WAIT_LIVE_MAX = 3 * 3600.0 # これより長くは待たない
NAME_CHARS = 40

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
# 反応だけのコメント（草・w・8888・拍手・顔文字だけなど）。1 件ずつには返さない
REACTION = re.compile(r'^[\s草wWｗＷ8８!！?？…ー〜♪☆★✨👏😂🤣😆😊😍💕❤️♡！]+$|^(かわいい|可愛い|かわいすぎ|きゃわ|ｗｗ+|おつ|乙|888+|８８８+)[!！。ー〜wｗ]*$')
GREETING = re.compile(r'^(こんにちは|こんばんは|おはよう|こん(ばん|にち)?(は|わ)|はじめまして|初見|しょけん|やっほ|ばんわ|hello|hi)[\s!！。ー〜です]*$',
                      re.IGNORECASE)
CALLS_CIEL = re.compile(r'シエル|しえる|ciel', re.IGNORECASE)
QUESTION = re.compile(r'[?？]|ですか|ますか|なに|何|どう|どこ|だれ|誰|いつ|なんで|なぜ|教えて')


def video_id(text: str) -> str | None:
    """配信の URL（watch?v=・youtu.be/・/live/・Studio の /video/…/livestreaming）か、11 文字の動画 ID から動画 ID を取り出す"""
    text = (text or '').strip()
    if VIDEO_ID.match(text):
        return text
    try:
        u = urlparse(text if '://' in text else 'https://' + text)
    except ValueError:
        return None
    host = (u.hostname or '').lower()
    if not (host == 'youtu.be' or host.endswith('youtube.com')):
        return None
    if host == 'youtu.be':
        cand = u.path.strip('/').split('/')[0]
        return cand if VIDEO_ID.match(cand) else None
    v = parse_qs(u.query).get('v', [''])[0]
    if VIDEO_ID.match(v):
        return v
    parts = [p for p in u.path.split('/') if p]
    for i, p in enumerate(parts[:-1]):
        if p in ('live', 'video', 'shorts', 'embed') and VIDEO_ID.match(parts[i + 1]):
            return parts[i + 1]
    return None


def kind_of(text: str) -> str:
    """コメントの種類：reaction（数えるだけ）・greeting（束ねて返す）・talk（溜めて選ぶ）"""
    t = text.strip()
    if not t or REACTION.match(t):
        return 'reaction'
    if GREETING.match(t):
        return 'greeting'
    return 'talk'


def clean(text: str, limit: int) -> str:
    """だれでも書ける文字。改行・角かっこを外して短くする（指示の区切りを作らせない）"""
    text = re.sub(r'[\r\n\t]+', ' ', text or '')
    text = text.replace('「', '『').replace('」', '』').replace('[', '［').replace(']', '］')
    return text.strip()[:limit]


class Comment:
    __slots__ = ('id', 'author', 'channel', 'text', 'at', 'kind', 'paid', 'first')

    def __init__(self, id, author, channel, text, at, kind, paid='', first=False):
        self.id, self.author, self.channel, self.text, self.at = id, author, channel, text, at
        self.kind, self.paid, self.first = kind, paid, first


def parse(item: dict, now: float) -> Comment | None:
    """liveChatMessage 1 件を Comment に。返さない種類（消された・BAN など）は None"""
    s = item.get('snippet') or {}
    a = item.get('authorDetails') or {}
    t = s.get('type')
    text = s.get('displayMessage') or ''
    paid = ''
    if t == 'superChatEvent':
        d = s.get('superChatDetails') or {}
        paid = f"スーパーチャット {d.get('amountDisplayString', '')}".strip()
        text = d.get('userComment') or ''
    elif t == 'superStickerEvent':
        d = s.get('superStickerDetails') or {}
        paid = f"スーパーステッカー {d.get('amountDisplayString', '')}".strip()
        text = ''
    elif t in ('newSponsorEvent', 'memberMilestoneChatEvent'):
        paid = 'メンバー加入' if t == 'newSponsorEvent' else 'メンバー継続'
        if t == 'memberMilestoneChatEvent':
            text = (s.get('memberMilestoneChatDetails') or {}).get('userComment') or ''
    elif t == 'membershipGiftingEvent':
        paid = 'メンバーシップのギフト'
    elif t != 'textMessageEvent':
        return None
    at = now
    try:
        at = datetime.fromisoformat((s.get('publishedAt') or '').replace('Z', '+00:00')).timestamp()
    except ValueError:
        pass
    author = clean(a.get('displayName') or '名無し', NAME_CHARS).lstrip('@') or '名無し'
    body = clean(text, TEXT_CHARS)
    return Comment(item.get('id'), author, a.get('channelId') or author, body, at,
                   'paid' if paid else kind_of(body), paid)


class Pool:
    """溜まっているコメント。話せる番に 1 つ（あいさつは束で）選ぶ。時計は差し替えられる（試験用）"""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.paid: deque[Comment] = deque()
        self.talk: list[Comment] = []
        self.greetings: list[Comment] = []
        self.reactions: deque[float] = deque()
        self.seen_authors: set[str] = set()
        self.recent: deque[str] = deque(maxlen=RECENT_AUTHORS)
        self.received = 0

    def add(self, c: Comment) -> None:
        self.received += 1
        c.first = c.channel not in self.seen_authors
        self.seen_authors.add(c.channel)
        if c.kind == 'paid':
            self.paid.append(c)
        elif c.kind == 'reaction':
            self.reactions.append(c.at)
        elif c.kind == 'greeting':
            self.greetings.append(c)
        else:
            last = self.talk[-1] if self.talk else None
            if last is not None and last.channel == c.channel and c.at - last.at <= MERGE_SECONDS:
                last.text = clean(last.text + ' ' + c.text, TEXT_CHARS)
                last.at = c.at
            else:
                self.talk.append(c)
                del self.talk[:-POOL_MAX]

    def _forget_old(self) -> None:
        now = self.clock()
        self.talk = [c for c in self.talk if now - c.at <= OLD_SECONDS]
        self.greetings = [c for c in self.greetings if now - c.at <= OLD_SECONDS]
        while self.reactions and now - self.reactions[0] > 60:
            self.reactions.popleft()

    def score(self, c: Comment) -> float:
        age = max(0.0, self.clock() - c.at)
        s = 1.0 - age / OLD_SECONDS                 # 新しいほど上
        if CALLS_CIEL.search(c.text):
            s += 0.8
        if QUESTION.search(c.text):
            s += 0.5
        if c.first:
            s += 0.3                                # 初めての人
        if c.channel in self.recent:
            s -= 0.7                                # 最近返した人
        return s

    def pick(self) -> dict | None:
        """次に返すもの：{'kind': 'paid'|'greeting'|'talk', 'comments': [...], 'reactions': 直近 1 分の反応の数}。無ければ None"""
        self._forget_old()
        if self.paid:
            chosen, kind = [self.paid.popleft()], 'paid'
        elif self.talk:
            best = max(self.talk, key=self.score)
            self.talk.remove(best)
            chosen, kind = [best], 'talk'
        elif self.greetings:
            names, chosen = set(), []
            for c in self.greetings:
                if c.channel not in names:
                    names.add(c.channel)
                    chosen.append(c)
            chosen, kind = chosen[:6], 'greeting'
            self.greetings.clear()
        else:
            return None
        for c in chosen:
            self.recent.append(c.channel)
        return {'kind': kind, 'comments': chosen, 'reactions': len(self.reactions)}

    def put_back(self, choice: dict) -> None:
        """返しそびれたものを戻す"""
        cs = choice['comments']
        if choice['kind'] == 'paid':
            self.paid.extendleft(reversed(cs))
        elif choice['kind'] == 'talk':
            self.talk.extend(cs)
        else:
            self.greetings[:0] = cs
        for c in cs:
            if c.channel in self.recent:
                self.recent.remove(c.channel)

    def waiting(self) -> int:
        self._forget_old()
        return len(self.paid) + len(self.talk) + (1 if self.greetings else 0)


def instructions(choice: dict, head: str) -> str:
    """選んだコメントに返す指示。返し方は config/prompts/comment.md（head）、コメントの中身は信用しない入力として JSON で付ける"""
    data = {
        'kind': choice['kind'],
        'comments': [{'author': c.author, 'text': c.text, 'first': c.first, **({'paid': c.paid} if c.paid else {})}
                     for c in choice['comments']],
        'reactions': choice['reactions'],
    }
    return head + '\n\n' + json.dumps(data, ensure_ascii=False)


class YouTubeChat:
    def __init__(self, say_when_free: Callable, *, history=None, notify: Callable[[dict], None] | None = None,
                 head: str = '', tool_choice: str | None = None, key: str | None = None) -> None:
        self.say_when_free = say_when_free   # mouth.Mouth.say_when_free
        self.history = history               # conversation.Conversation（返したコメントを発言として入れる）
        self.notify = notify                 # アプリへの知らせ（youtube.state）
        self.head = head                     # 指示の頭（config/prompts/comment.md）
        self.tool_choice = tool_choice       # 心の無い組み立てでは 'none'（道具を使わせない）
        # 環境変数は会話サーバーが .env を読んだあと（作るとき）に読む
        self.key = os.environ.get('YOUTUBE_API_KEY', '') if key is None else key
        self.poll = float(os.environ.get('YOUTUBE_POLL_SECONDS') or POLL_SECONDS)
        self.pool = Pool()
        self.state, self.reason, self.title, self.video = 'off', '', '', ''
        self._task: asyncio.Task | None = None
        self._replier: asyncio.Task | None = None
        self._arrived = asyncio.Event()
        self.replied = 0
        self._recorded: set = set()   # 会話の記録に入れたコメント（返しそびれて選び直したとき、二重に入れない）

    # ---- アプリから ----

    def on_data(self, packet) -> None:
        if getattr(packet, 'topic', None) != TOPIC:
            return
        try:
            m = json.loads(packet.data.decode('utf-8'))
        except (ValueError, AttributeError, UnicodeDecodeError):
            return
        if not isinstance(m, dict) or m.get('type') != 'youtube.link':
            return
        if m.get('on') and m.get('url'):
            self.start(str(m['url']))
        else:
            asyncio.create_task(self.stop())

    def publish(self) -> None:
        if self.notify is not None:
            self.notify({'v': VERSION, 'type': 'youtube.state', 'state': self.state, 'reason': self.reason,
                         'title': self.title, 'video': self.video, 'received': self.pool.received,
                         'replied': self.replied})

    def _set(self, state: str, reason: str = '') -> None:
        self.state, self.reason = state, reason
        log.info('YouTube のコメント：%s %s', state, reason)
        debug_log.record('youtube', state=state, reason=reason)
        self.publish()

    def start(self, url: str) -> None:
        vid = video_id(url)
        if vid is None:
            self._set('error', 'bad_url')
            return
        if vid == self.video and self._task is not None and not self._task.done():
            self.publish()
            return
        asyncio.create_task(self._restart(vid))

    async def _restart(self, vid: str) -> None:
        await self.stop(quiet=True)
        if not self.key:
            self.video = vid
            self._set('error', 'no_key')
            return
        self.video, self.title, self.pool = vid, '', Pool()
        self._set('connecting')
        self._task = asyncio.create_task(self._run(vid))
        self._replier = asyncio.create_task(self._reply_loop())

    async def close(self) -> None:
        """会話の終わり（アプリへは知らせない）"""
        await self.stop(quiet=True)

    async def stop(self, quiet: bool = False) -> None:
        for t in (self._task, self._replier):
            if t is not None and not t.done():
                t.cancel()
        for t in (self._task, self._replier):
            if t is not None:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        self._task = self._replier = None
        if not quiet:
            self.video = self.title = ''
            self._set('off')

    # ---- 取り込み ----

    async def _get(self, http: aiohttp.ClientSession, path: str, **params) -> tuple[int, dict]:
        return await read_youtube(http, API, self.key, path, params, timeout=HTTP_TIMEOUT)

    @staticmethod
    def _error_reason(body: dict) -> str:
        errors = ((body.get('error') or {}).get('errors') or [{}])
        return errors[0].get('reason') or 'http_error'

    async def _run(self, vid: str) -> None:
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as http:
                chat_id = await self._find_chat(http, vid)
                if not chat_id:
                    return
                page, first, fails = None, True, 0
                while True:
                    params = {'liveChatId': chat_id, 'part': 'snippet,authorDetails', 'maxResults': 500}
                    if page:
                        params['pageToken'] = page
                    try:
                        status, body = await self._get(http, 'liveChat/messages', **params)
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        fails += 1
                        log.info('YouTube のコメントを読めない（%s）。%d 回目', type(e).__name__, fails)
                        await asyncio.sleep(min(60, self.poll * fails))
                        continue
                    if status != 200:
                        reason = self._error_reason(body)
                        if reason in ('rateLimitExceeded',) or status >= 500:
                            await asyncio.sleep(self.poll * 2)
                            continue
                        self._set('error', reason)   # liveChatEnded・quotaExceeded・forbidden など
                        return
                    fails = 0
                    if self.state != 'live':
                        self._set('live')
                    self._take(body.get('items') or [], backlog=first)
                    first = False
                    page = body.get('nextPageToken') or page
                    if body.get('offlineAt'):
                        self._set('error', 'liveChatEnded')
                        return
                    wait = max(self.poll, (body.get('pollingIntervalMillis') or 0) / 1000)
                    await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning('YouTube のコメントの取り込みが止まった error=%s', type(e).__name__)
            self._set('error', 'failed')

    async def _find_chat(self, http: aiohttp.ClientSession, vid: str) -> str | None:
        """動画のコメント欄の ID。予約した配信が始まっていなければ、始まるまで WAIT_LIVE 秒ごとに見直す（1 回 1 単位）"""
        started = time.monotonic()
        while True:
            try:
                status, body = await self._get(http, 'videos', part='snippet,liveStreamingDetails', id=vid)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                status, body = 0, {}
            if status == 0 or status >= 500:
                await asyncio.sleep(WAIT_LIVE)
                continue
            if status != 200:
                self._set('error', self._error_reason(body))
                return None
            items = body.get('items') or []
            if not items:
                self._set('error', 'not_found')   # 無い・非公開
                return None
            self.title = clean((items[0].get('snippet') or {}).get('title') or '', 80)
            live = items[0].get('liveStreamingDetails')
            if live is None:
                self._set('error', 'not_live')    # 配信ではない動画
                return None
            if live.get('actualEndTime'):
                self._set('error', 'liveChatEnded')
                return None
            if live.get('activeLiveChatId'):
                return live['activeLiveChatId']
            if time.monotonic() - started > WAIT_LIVE_MAX:
                self._set('error', 'not_started')
                return None
            if self.state != 'waiting':
                self._set('waiting', 'not_started')   # 予約した配信が始まるのを待つ
            await asyncio.sleep(WAIT_LIVE)

    def _take(self, items: list, backlog: bool) -> None:
        now = time.time()
        added = 0
        for item in items:
            c = parse(item, now)
            if c is None:
                continue
            if backlog and now - c.at > BACKLOG_SECONDS:
                self.pool.seen_authors.add(c.channel)   # つなぐ前から来ていた人は、初見にしない
                continue
            self.pool.add(c)
            added += 1
        if added:
            self._arrived.set()
            self.publish()

    # ---- 返す ----

    async def _reply_loop(self) -> None:
        while True:
            if not self.pool.waiting():
                self._arrived.clear()
                await self._arrived.wait()
                continue
            choice = self.pool.pick()
            if choice is None:
                continue
            kwargs = {'instructions': instructions(choice, self.head)}
            if self.tool_choice is not None:
                kwargs['tool_choice'] = self.tool_choice
            self._record(choice)
            try:
                handle = await self.say_when_free('comment', wait=WAIT_FREE, settle=SETTLE, **kwargs)
            except Exception as e:
                log.warning('コメントに返せない error=%s', type(e).__name__)
                handle = None
            if handle is None:
                self.pool.put_back(choice)   # 切れ目が来なかった。次の番にまた選ぶ（古くなれば捨てる）
            else:
                self.replied += 1
                self.publish()
                try:
                    await handle   # 話し終えるまで待つ
                except Exception:
                    pass
            await asyncio.sleep(GAP_SECONDS)

    def _record(self, choice: dict) -> None:
        """返すコメントを、会話の記録に「コメント・名前」の発言として入れる（心が前後の流れを読めるように）"""
        if self.history is None:
            return
        for c in choice['comments']:
            if c.id in self._recorded:
                continue
            self._recorded.add(c.id)
            turn = self.history.reserve(role='user')
            text = c.text or ''
            if c.paid:
                text = f'（{c.paid}）{text}'.strip()
            self.history.complete(turn, text or '（あいさつ）', label=f'コメント・{c.author}')
