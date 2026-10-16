# -*- coding: utf-8 -*-
"""感情：会話モデルが文の頭に付けた印（例 [happy]）を読み取り、声の説明（キャプション）と、Unity の表情に使う。

- 会話モデルには、config/prompts/emotion.md で印の付け方を教える。
- tts_node：届いた文字を 1 文ずつに分け、印を外して Irodori-TTS で読み上げる。その文の声を流し始めるときに、
  Unity へ表情のイベント（仕様書 6 章の character.expression）を LiveKit のデータのメッセージで送る。
- transcription_node：文字起こしから印を外す。
印の無い文は、直前の感情のまま。返事の始まりは通常（neutral）。
会話モデル（gpt-realtime-2.1-mini）は、まれに印を崩す（2026-10-16 の試験で数十文に 3 回ほど）。read_tags が拾う：
  かっこの無い印（「happy ところで」）・かっこの中の空白や大文字（「[ Happy ]」）… その感情として読み、外す。
  一覧に無い印（「[happily]」）・途中で切れた印（「[h]」）… 一覧の名前と頭が合い、1 つに決まればその感情。決まらなければ直前のまま。
  漏れた話者の 1 行（「[発言者：…]」）… 外す。
"""
import json
import logging
import re
import time
from collections.abc import AsyncIterable

import aiohttp
import numpy as np
from livekit import rtc
from livekit.agents import get_job_context

import irodori_tts

log = logging.getLogger('ciel-agent.emotion')

BASE = ('柔らかく朗らかな響きを持つ10代前半の少女。人懐っこく甘すぎないナチュラルなトーンで、聞く人を笑顔にする温かみのある声。'
        '無邪気で親しみやすく、一生懸命寄り添ってくれるパートナー風。')
# 感情 → Irodori-TTS の声の説明。troubled・sad は設定資料 7.1 の「困っているとき」「失敗して焦っているとき」をもとにした
CAPTIONS = {
    'neutral': BASE,
    'happy': '柔らかく朗らかな響きを持つ10代前半の少女。うれしくて声が弾む、明るく元気な笑顔の声。人懐っこく温かい。',
    'relaxed': '柔らかくナチュラルなトーンの10代前半の少女。ほっとして穏やかな、にこにこした落ち着いた声。ゆったりとやさしい。',
    'surprised': '柔らかな響きを持つ10代前半の少女。思わず声が裏返るほどびっくりした、勢いのある驚きの声。少し早口。',
    'angry': '柔らかな響きを持つ10代前半の少女。ほっぺたをふくらませて、ぷんすか怒っている声。本気ではなく可愛らしく拗ねたトーン。',
    'sad': '柔らかなトーンの10代前半の少女。しょんぼりして元気がない、小さく沈んだ声。ゆっくりめで弱々しい。',
    'troubled': ('柔らかくナチュラルなトーンの10代前半の少女。いつもの明るさは控えめで、少し困り顔で考え込んでいる声。'
                 '切なさと困惑が混ざったような弱めの発声で、相手に申し訳なさそうに寄り添うトーン。'),
    'embarrassed': '柔らかな響きを持つ10代前半の少女。照れて恥ずかしそうな、もじもじした小さめの声。少しはにかんで早口。',
    'teary': '柔らかな響きを持つ10代前半の少女。涙をこらえて声が震える、半泣きの声。鼻声ぎみで、けなげに話す。',
    'excited': '柔らかく朗らかな響きを持つ10代前半の少女。目を輝かせてわくわくしている、はしゃいだ高めの声。勢いがあって楽しそう。',
    'jitome': '柔らかなトーンの10代前半の少女。じとっと疑うような、少し不満げで平たい声。ゆっくりめ。',
    'thinking': '柔らかくナチュラルなトーンの10代前半の少女。うーんと考えながら話す、ゆっくりとした落ち着いた声。',
}
NAMES = '|'.join(CAPTIONS)
TAG = re.compile(r'\[\s*([A-Za-z]+)\s*\]')
# かっこの無い印：文の頭（返事の始め・改行・文の終わりのあと）にある感情の名前で、すぐ後が日本語のもの
BARE_TAG = re.compile(rf'(^|[\n。！？!?])[ \t　]*({NAMES})(?![A-Za-z])[ \t　]*(?=[^\x00-\x7f])', re.IGNORECASE)
TRAILING_WORD = re.compile(r'(^|[\n。！？!?])([ \t　]*[A-Za-z]+[ \t　]*)$')   # 文字起こしで持ち越す、文の頭の英字
# 崩れた印（閉じていない「[happ」や、残った「]」）。会話モデルがまれに崩した印を出すので、読み上げないように外す
BROKEN_TAG = re.compile(r'\[\s*[A-Za-z]*\s*(?![A-Za-z\]])|\]')
# 返事に漏れた話者の 1 行（turns.py が足す「[発言者：…]」。かっこが無いこともある）
SPEAKER_LINE = re.compile(r'\[?発言者：[^\]\n]*?(?:）\]?|\])')
SENTENCE_END = re.compile(r'[。！？!?\n]+|……')
MIN_SENTENCE = 4   # これより短い文は、次の文とまとめて読む


class ExpressionEvents:
    """Unity へ表情のイベントを送る（音声とは別のデータのメッセージ。遅れても音声を止めない）。"""

    def __init__(self) -> None:
        self.seq = 0

    async def send(self, expression: str, ttl_ms: int) -> None:
        ctx = get_job_context(required=False)
        if ctx is None:
            return
        self.seq += 1
        msg = {'v': 1, 'type': 'character.expression', 'seq': self.seq,
               'expression': expression, 'intensity': 1.0, 'ttl_ms': ttl_ms}
        try:
            await ctx.room.local_participant.publish_data(json.dumps(msg), reliable=True, topic='ciel.event')
        except Exception as e:   # 表情が送れなくても、話は続ける
            log.warning('表情のイベントを送れない: %s', e)


def strip_tags(text: str) -> str:
    """印を外す。崩れた印（最後に残った書きかけの「[happy」、閉じていない「[happ博士…」、残った「]」、
    かっこの無い「happy ところで」）と、漏れた話者の 1 行も外す"""
    text = BARE_TAG.sub(lambda m: m.group(1), SPEAKER_LINE.sub('', text))
    return BROKEN_TAG.sub('', TAG.sub('', text))


def resolve(word: str) -> str | None:
    """印の言葉を、一覧の感情にする。一覧に無ければ、頭が合う名前（どちらかがもう一方の頭か、頭の 4 文字が同じ）が
    1 つだけのときその感情（happily → happy、h → happy、sadness → sad）"""
    word = word.lower()
    if word in CAPTIONS:
        return word
    hits = [n for n in CAPTIONS if n.startswith(word) or word.startswith(n) or (len(word) >= 4 and n[:4] == word[:4])]
    return hits[0] if len(hits) == 1 else None


def read_tags(sentence: str) -> tuple[str | None, str]:
    """文の印を読む。（最後に読めた感情、または None, 印を外した本文）"""
    emotion = None
    found = [(m.start(2), m.group(2)) for m in BARE_TAG.finditer(sentence)]
    found += [(m.start(1), m.group(1)) for m in TAG.finditer(sentence)]
    for _, word in sorted(found):
        emotion = resolve(word) or emotion
    return emotion, strip_tags(sentence).strip()


def split_sentences(buf: str) -> tuple[list[str], str]:
    """buf から、終わりの記号まで揃った文を取り出す。（文のリスト, 残り）"""
    out, start = [], 0
    for m in SENTENCE_END.finditer(buf):
        piece = buf[start:m.end()]
        if len(strip_tags(piece).strip()) >= MIN_SENTENCE:
            out.append(piece)
            start = m.end()
    return out, buf[start:]


async def synthesize(session: aiohttp.ClientSession, text: str, caption: str) -> tuple[bytes, int]:
    async with session.post(irodori_tts.URL, json={'text': text, 'caption': caption},
                            timeout=aiohttp.ClientTimeout(total=30)) as r:
        r.raise_for_status()
        return await r.read(), int(r.headers.get('X-Sample-Rate', '48000'))


def frames(pcm: bytes, sr: int):
    data = np.frombuffer(pcm, dtype='<i2')
    n = sr // 50   # 20 ms
    for i in range(0, len(data), n):
        chunk = data[i:i + n]
        yield rtc.AudioFrame(chunk.tobytes(), sr, 1, len(chunk))


async def tts_node(text: AsyncIterable[str], events: ExpressionEvents):
    """1 文ずつ：印を読み取り、その感情の声で読み上げ、声を流し始めるときに表情を送る。"""
    emotion = 'neutral'
    buf = ''

    async def speak(sentence: str):
        nonlocal emotion
        found, body = read_tags(sentence)
        emotion = found or emotion
        if not body:
            return
        t0 = time.perf_counter()
        pcm, sr = await synthesize(http, body, CAPTIONS[emotion])
        dur_ms = int(len(pcm) / 2 / sr * 1000)
        log.info('[%s] 合成 %.2f 秒：%s', emotion, time.perf_counter() - t0, body[:30])
        await events.send(emotion, ttl_ms=dur_ms + 1500)
        for f in frames(pcm, sr):
            yield f

    async with aiohttp.ClientSession() as http:
        async for chunk in text:
            buf += chunk
            done, buf = split_sentences(buf)
            for s in done:
                async for f in speak(s):
                    yield f
        if strip_tags(buf).strip():
            async for f in speak(buf):
                yield f


async def transcription_node(text: AsyncIterable):
    """文字起こしから印を外す。印が chunk の境目で切れても外せるよう、[ から ] までと、
    文の頭の英字（かっこの無い印かもしれない）は持ち越す。"""
    pending = ''
    async for chunk in text:
        s = pending + str(chunk)
        cut = s.rfind('[')
        if cut == -1 or ']' in s[cut:]:
            m = TRAILING_WORD.search(s)
            cut = m.start(2) if m else -1
        if cut != -1:
            s, pending = s[:cut], s[cut:]
        else:
            pending = ''
        s = strip_tags(s)
        if s:
            yield s
    if pending:
        yield strip_tags(pending)
