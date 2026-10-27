# -*- coding: utf-8 -*-
"""感情：会話モデルが文の頭に付けた印（例 [happy]）を読み取り、声の説明（キャプション）・文に入れる絵文字と、Unity の表情に使う。

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
import latency

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
# 感情 → 文に入れる絵文字。Irodori-TTS が読み方の指示として学んだもの（モデルの EMOJI_ANNOTATIONS.md の意味から選んだ）。
# キャプションだけより感情がはっきり出る（2026-10-18 の聞き比べ、server/tts-irodori/compare_emotions.py）
EMOJI = {
    'happy': '😊',        # Cheerfully, gladly
    'relaxed': '😌',      # Relieved, contentedly
    'surprised': '😲',    # Surprise, awe / exclamation
    'angry': '😠',        # Angry, displeased, sulking
    'sad': '🥺',          # Trembling voice, timidly / uncertainly
    'troubled': '😟',     # Anxiously, worriedly
    'embarrassed': '🫣',  # Shyly, bashfully
    'teary': '😭',        # Sobbing, crying, sorrowfully / sadly
    'excited': '😆',      # Joyfully, happily
    'jitome': '🙄',       # Exasperatedly, rolling eyes
    'thinking': '🤔',     # Questioning voice, wondering
}
# 効き方：キャプションを強め（既定 3.0）、参照音声を弱める（既定 5.0）。参照音声は通常の声なので、既定では感情が出にくかった。
# 絵文字と合わせると、どちらか片方より感情がよく出た（同じ聞き比べ）
STYLE = {'cfg_caption': 5.0, 'cfg_speaker': 3.5}
NAMES = '|'.join(CAPTIONS)
TAG =re.compile(r'\[\s*([A-Za-z]+)\s*\]')
# かっこの無い印：文の頭（返事の始め・改行・文の終わりのあと）にある感情の名前で、すぐ後が日本語のもの
BARE_TAG = re.compile(rf'(^|[\n。！？!?])[ \t　]*({NAMES})(?![A-Za-z])[ \t　]*(?=[^\x00-\x7f])', re.IGNORECASE)
TRAILING_WORD = re.compile(r'(^|[\n。！？!?])([ \t　]*[A-Za-z]+[ \t　]*)$')   # 文字起こしで持ち越す、文の頭の英字
# 崩れた印（閉じていない「[happ」や、残った「]」）。会話モデルがまれに崩した印を出すので、読み上げないように外す
BROKEN_TAG = re.compile(r'\[\s*[A-Za-z]*\s*(?![A-Za-z\]])|\]')
# 返事に漏れた話者の 1 行（turns.py が足す「[発言者：…]」。かっこが無いこともある）
SPEAKER_LINE = re.compile(r'\[?発言者：[^\]\n]*?(?:）\]?|\])')
SENTENCE_END = re.compile(r'[。！？!?\n]+|……')
TAIL = re.compile(r'[。！？!?…\s]*$')   # 絵文字は文の終わりの記号の前に入れる
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


def with_emoji(text: str, emotion: str) -> str:
    """感情の絵文字を、文の終わりの記号の前に入れる（neutral は入れない）"""
    m = TAIL.search(text)
    return text[:m.start()] + EMOJI.get(emotion, '') + text[m.start():]


async def synthesize(session: aiohttp.ClientSession, text: str, caption: str,
                     seconds: float | None = None, style: dict | None = None) -> tuple[bytes, int]:
    """読み上げる。seconds を渡すと、その長さの音声にする（省略すると Irodori-TTS が決める）。
    style は効き方（STYLE。省略すると Irodori-TTS の既定）"""
    body = {'text': text, 'caption': caption} | ({} if seconds is None else {'seconds': seconds}) | (style or {})
    return await irodori_tts.request_audio(session, body)


def frames(pcm: bytes, sr: int):
    data = np.frombuffer(pcm, dtype='<i2')
    n = sr // 50   # 20 ms
    for i in range(0, len(data), n):
        chunk = data[i:i + n]
        yield rtc.AudioFrame(chunk.tobytes(), sr, 1, len(chunk))


class PreambleCut:
    """道具を呼んだ返事の前置きを、読み上げている 1 文のあとで止める（tools/singing.py・tools/minutes.py が頼む）。
    歌を聴く・議事録をとる道具は、すぐ戻って、あとから短い一言（「どうぞ」「議事録、とり始めますね」）を言わせる。
    会話モデルが同じ返事で前置きを何文も話すと、その一言が前置きを読み終えるまで待たされた（2026-10-27、「どうぞ」まで 22 秒）。
    LiveKit は道具を読み上げと並べて動かすので、道具が呼ばれた時点では前置きはまだ読み上げの途中にある。
    読み上げは 1 文ずつ、流し終える少し前に次の文を作るので、次の文を作る前に止める。止めるのは頼んだ返事だけ（返事の ID で見分ける）"""

    def __init__(self) -> None:
        self._speech_id: str | None = None

    def request(self, speech) -> None:
        self._speech_id = getattr(speech, 'id', None)

    def stop(self, speech_id: str | None) -> bool:
        return speech_id is not None and speech_id == self._speech_id


async def tts_node(text: AsyncIterable[str], events: ExpressionEvents, backchannel=None, stop=None):
    """1 文ずつ：印を読み取り、その感情の声で読み上げ、声を流し始めるときに表情を送る。
    すぐ前に相づち（aizuchi.py）を流していたら、最初の文の頭の相づちを外す。
    stop() が True になったら、次の文からは読まない（残りの文字は受け取って捨てる。PreambleCut）"""
    emotion = 'neutral'
    buf = ''
    first = True
    spoken = 0
    dropped = 0

    def stopped() -> bool:
        return stop is not None and stop()

    async def speak(sentence: str):
        nonlocal emotion, first
        found, body = read_tags(sentence)
        emotion = found or emotion
        if first and backchannel is not None and body:
            body = backchannel.strip(body)
        first = first and not body
        if not body:
            return
        t0 = time.perf_counter()
        latency.mark('最初の文')
        pcm, sr = await synthesize(http, with_emoji(body, emotion), CAPTIONS[emotion], style=STYLE)
        latency.mark('最初の声')
        dur_ms = int(len(pcm) / 2 / sr * 1000)
        log.info('[%s] 合成 %.2f 秒', emotion, time.perf_counter() - t0)
        if backchannel is not None:
            await backchannel.wait()   # 相づちが鳴り終わってから話す
        await events.send(emotion, ttl_ms=dur_ms + 1500)
        for f in frames(pcm, sr):
            yield f

    async with aiohttp.ClientSession() as http:
        async for chunk in text:
            latency.mark('最初の文字')
            buf += chunk
            done, buf = split_sentences(buf)
            for s in done:
                if stopped():
                    dropped += len(strip_tags(s))
                    continue
                spoken += 1
                async for f in speak(s):
                    yield f
        if strip_tags(buf).strip():
            if stopped():
                dropped += len(strip_tags(buf))
            else:
                async for f in speak(buf):
                    yield f
        if dropped:
            log.info('道具を呼んだ返事の前置きを止めた（%d 文を読んだあと、残り %d 字を読まない）', spoken, dropped)


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
