# -*- coding: utf-8 -*-
"""シエルの目：持ち主がアプリから送った画像を受け取り、心に見せる。docs/vision-design-ja.md。

- アプリは画像を縮めて JPEG にし、LiveKit のファイル送信（topic ciel.image）で送る。ここで受け取り、直近 KEEP 枚をメモリーにだけ持つ
  （保存しない。デバッグ用の会話ログにも、大きさと種類だけ）。
- 届いたら、口の why 'image' で、話の切れ目にシエルが見て話す。心がその返事にだけ画像を添える（mind.py の build）。
  届いた直後に持ち主が「これどう？」と話したときも、その返事で見る（見ていない画像があれば心に回す）。
- 一度見たら、軽いモデルが短い説明文を書く。あとの返事には説明文だけを「[見せてもらった画像]」で渡し、画像は送り直さない。
  「さっきの絵の…」のように画像を指したときだけ、もう一度添える。
"""
import asyncio
import base64
import itertools
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable

import openai
from livekit.agents import llm

import debug_log
import models

log = logging.getLogger('ciel-agent.eyes')

TOPIC = 'ciel.image'
MAX_BYTES = 3_000_000
KEEP = 3                 # メモリーに持つ枚数
RECALL_SECONDS = 600.0   # 画像を指した話で、もう一度添えるのは、この秒数のうちに見せてもらった画像だけ
SETTLE = 1.0             # 持ち主がこの秒数だまってから見て話す（送りながら「これどう？」と言うことが多い）
CAPTION_TIMEOUT = 20.0
CAPTION_CHARS = 240
# 画像を指す言葉（もう一度見る）
LOOK_AGAIN = re.compile(r'(さっき|その|あの|この|今の|いまの)(画像|絵|写真|スクショ|イラスト|画面)|(画像|絵|写真|スクショ|イラスト)(の|で|に|を|って)')
MAGIC = ((b'\xff\xd8\xff', 'image/jpeg'), (b'\x89PNG\r\n\x1a\n', 'image/png'), (b'RIFF', 'image/webp'))


def mime_of(data: bytes) -> str | None:
    """先頭のバイト列から画像の種類を決める（アプリが言う種類は信じない）"""
    for magic, mime in MAGIC:
        if data.startswith(magic) and (mime != 'image/webp' or data[8:12] == b'WEBP'):
            return mime
    return None


@dataclass
class Picture:
    id: int
    data_url: str
    name: str
    size: int
    at: float
    seen: bool = False
    caption: str | None = None


class Eyes:
    def __init__(self, say: Callable[..., None], caption_instructions: str = '', *, client=None,
                 notify: Callable[[dict], None] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.say = say                     # mouth.Mouth.say_latest
        self.caption_instructions = caption_instructions   # config/prompts/image_caption.md
        self.notify = notify               # アプリへの知らせ（image.state）
        self.pictures: list[Picture] = []
        self._client = client
        self._clock = clock
        self._ids = itertools.count(1)
        self._tasks: set[asyncio.Task] = set()

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    # ---- 受け取る ----

    def on_stream(self, reader, participant_identity: str) -> None:
        """LiveKit の register_byte_stream_handler に渡す"""
        self._spawn(self._receive(reader))

    async def _receive(self, reader) -> None:
        chunks, size = [], 0
        try:
            async for chunk in reader:
                size += len(chunk)
                if size > MAX_BYTES:
                    self._state('failed', reason='too_large')
                    return
                chunks.append(chunk)
        except Exception as e:
            log.info('画像を受け取れない：%s', type(e).__name__)
            self._state('failed', reason='error')
            return
        name = getattr(getattr(reader, 'info', None), 'name', '') or ''
        self.receive(b''.join(chunks), name)

    def receive(self, data: bytes, name: str = '') -> Picture | None:
        mime = mime_of(data)
        if mime is None:
            self._state('failed', reason='not_image')
            return None
        pic = Picture(next(self._ids), f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}',
                      name[:80], len(data), self._clock())
        self.pictures = (self.pictures + [pic])[-KEEP:]
        log.info('画像を受け取った（#%d、%d バイト、%s）', pic.id, pic.size, mime)
        debug_log.record('image', id=pic.id, bytes=pic.size, mime=mime)
        self._state('received', id=pic.id)
        self.say('image', settle=SETTLE, instructions=f'[持ち主が画像を見せてくれた（#{pic.id}）]')
        return pic

    # ---- 心へ ----

    def wants(self, text: str) -> bool:
        """この返事で画像を見るか（心に回すか）"""
        return self._pick(text) is not None

    def _pick(self, text: str) -> Picture | None:
        unseen = [p for p in self.pictures if not p.seen]
        if unseen:
            return unseen[-1]
        if text and LOOK_AGAIN.search(text):
            recent = [p for p in self.pictures if self._clock() - p.at <= RECALL_SECONDS]
            return recent[-1] if recent else None
        return None

    def message_for_reply(self, text: str) -> llm.ChatMessage | None:
        """心の返事に添える画像（無ければ None）。添えたら見たことにし、説明文がまだなら書きに行く"""
        pic = self._pick(text)
        if pic is None:
            return None
        pic.seen = True
        if pic.caption is None and self.caption_instructions:
            self._spawn(self._caption(pic))
        debug_log.record('image_shown', id=pic.id)
        return llm.ChatMessage(role='user', content=[f'[見せてもらった画像 #{pic.id}{"（" + pic.name + "）" if pic.name else ""}]',
                                                     llm.ImageContent(image=pic.data_url, inference_detail='auto')])

    def context(self) -> str | None:
        """心と小脳へ渡す「[見せてもらった画像]」（説明文のあるものだけ。無ければ None）"""
        rows = [p for p in self.pictures if p.caption]
        if not rows:
            return None
        now = self._clock()
        lines = ['[見せてもらった画像]']
        for p in rows:
            ago = int(now - p.at)
            when = f'{ago} 秒前' if ago < 60 else f'{ago // 60} 分前'
            lines.append(f'#{p.id}（{when}）：{p.caption}')
        return '\n'.join(lines)

    # ---- 説明文 ----

    async def _caption(self, pic: Picture) -> None:
        model = models.model('eyes')
        try:
            r = await self.client.chat.completions.create(
                model=model, timeout=CAPTION_TIMEOUT,
                messages=[{'role': 'system', 'content': self.caption_instructions},
                          {'role': 'user', 'content': [{'type': 'image_url',
                                                        'image_url': {'url': pic.data_url, 'detail': 'low'}}]}])
            models.record('eyes', model, getattr(r, 'usage', None))
            text = ' '.join((r.choices[0].message.content or '').split())
        except Exception as e:   # 書けなくても会話は続ける（画像を指した話では、画像そのものをもう一度見る）
            log.warning('画像の説明文を書けない：%s', type(e).__name__)
            return
        if text:
            pic.caption = text[:CAPTION_CHARS]
            log.info('画像の説明文を書いた（#%d）', pic.id)

    # ---- そのほか ----

    def _state(self, state: str, **fields) -> None:
        if self.notify is not None:
            self.notify({'v': 1, 'type': 'image.state', 'state': state, **fields})

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def refuse(notify: Callable[[dict], None]) -> Callable:
    """画像を見られない会話サーバー（pipeline でない）：受け取ったら、見られないと返す"""
    def on_stream(reader, participant_identity: str) -> None:
        notify({'v': 1, 'type': 'image.state', 'state': 'failed', 'reason': 'unavailable'})
    return on_stream

