# -*- coding: utf-8 -*-
"""相づち：相手の発言に返事をするとき、返事の声ができるまでのあいだに、短い相づち（「うん。」など）を先に流す。

- 話し終わりから返事の声が届くまで、会話モデルが書き始めるまで（約 0.65 秒）と最初の文の読み上げ（約 0.5 秒）が
  かかる（2026-10-17、bench_latency.py）。そのあいだ黙っていると、聞こえたのかが分からず、言い直すと返事が
  取り消されて作り直しになっていた。相づちは会話の始めに読み上げておいた声を使うので、返事を頼むのと同時に流せる。
- 流すのは、相手の発言への返事のときだけ（turns.py が play() を呼ぶ）。短い発言（「おはよう」「うん」）・ひかえめ
  （黙ると決めることがある）・タッチ・自分から話しかけるとき・あいさつには流さない。
- 相手の発言が質問なら考えるときの相づち（「えっと、」「んーっと、」など）、それ以外は聞いたときの相づち（「うん。」など）。
  直前と同じ言葉は続けない。
- 聞いたときの相づちは、会話の始め（あいさつのあと）に、長さを決めて読み上げる（Irodori-TTS に長さを決めさせると間延びする）。
- 考えるときの相づちは、利用者が聞いて選んだ読み上げ（THINK_DIR の wav）をそのまま使う。長さを決めて読み上げると、
  考えているニュアンス（「えーっと……」）が消え、明るく短く返事をする声になった。声の説明（考え込む・語尾をのばす）と
  長さ（0.8・1.0 秒）を変えて読み上げた中から、考えている雰囲気のものを選んでもらった（2026-10-17）。読み上げは毎回
  少し違い、同じ指定でも語尾が途切れる・「ん」が高く元気な返事に聞こえるものがあるので、読み上げ直さずにファイルで持つ。
  ファイル名は「番号-言葉-声の説明-長さ-何回目.wav」。
  質問かは文字起こしで見る。文字起こしは区切りから 0.3〜0.5 秒で届くので、TEXT_WAIT_SECONDS まで待ってから選ぶ
  （待たずに選ぶと、質問にも「うんうん」と返していた）。
- 声は、シエルの声とは別のトラック（TRACK）で送る。アプリは両方を鳴らし、口パクは大きいほうに合わせる
  （CielConversation.cs）。LiveKit の話す順番（SpeechHandle）を通すと、相づちを流し終えるまで返事を頼めず、
  返事がその分（約 0.5 秒）遅れる。シエルの声のトラック（RoomIO の音声の出口）へ横から入れると、LiveKit の再生の管理と
  ぶつかり、何回か流すうちに返事の声が途中から届かなくなった（2026-10-17、bench_latency.py）。
  相手が話し始めたら止める（turns.py が stop() を呼ぶ）。
- 相手が長く話している途中の息つぎにも、聞いたときの相づちを打つ（nod()。息つぎを見つけるのは turns.py）。
- 相づちを流した返事は、最初の文の頭の同じような相づち（「うん、」「えっと、」）を外して読む（二重にならないように。emotion.py）。
"""
import asyncio
import logging
import random
import re
import time
import wave
from pathlib import Path

import aiohttp
import numpy as np
from livekit import rtc

import emotion

log = logging.getLogger('ciel-agent.aizuchi')

TRACK = 'ciel-aizuchi'
SAMPLE_RATE = 48000
# 聞いたときの相づちと、その長さ（秒）。Irodori-TTS に長さを決めさせると間延びした（「うん、うん。」1.0 秒など）
HEARD = {'うん。': 0.5, 'うんうん。': 0.7, 'うん、うん。': 0.9}
# 考えるとき（質問に答える前）の相づち：利用者が選んだ読み上げ
THINK_DIR = Path(__file__).resolve().parent / 'config' / 'aizuchi' / 'think'
CAPTION = emotion.BASE + '相手の話にうなずきながら、小さくやさしく相づちを打つ。'
# 相づちの長さの上限（前後の無音を除いて。念のため）。長すぎたら読み上げ直す
MAX_SECONDS = 1.2
TRIES = 3
# 前後の無音を除くときの、声とみなす大きさ
SILENCE_DB = -40.0
# 相づちを選ぶ前に、文字起こしを待つ時間（返事を頼んでから）
TEXT_WAIT_SECONDS = 0.3
# 相づちを流してから、これより後に始まった返事では、頭の相づちを外さない（別の返事かもしれない）
STRIP_SECONDS = 4.0
QUESTION = re.compile(r'[?？]\s*$|(?:の|か|かな|って)[。]?\s*$')
# 返事の最初の文の頭の相づち（相づちを流したときは外す）
LEADING = re.compile(r'^\s*(?:(?:うん|ええと|えー?っと|えーと|ん[ー〜]*っと|んー+|うーん)(?:ね)?[、。！!…〜ー]*\s*)+')


class Backchannel:
    def __init__(self, volume) -> None:
        self.volume = volume   # volume.VoiceVolume（設定画面で選んだ声の大きさ）
        self._source: rtc.AudioSource | None = None
        self._voices: dict[str, list[rtc.AudioFrame]] = {}   # 聞いたときの相づち（言葉 → 声）
        self._think: dict[str, list[rtc.AudioFrame]] = {}    # 考えるときの相づち（ファイル名 → 声）
        self._question = False
        self._heard = asyncio.Event()   # この発言の文字起こしが届いた
        self._last: str | None = None
        self._played_at: float | None = None
        self._task: asyncio.Task | None = None

    async def prepare(self, room: rtc.Room) -> None:
        """相づちのトラックを出し、相づちの声を読み上げておく（会話の始め、あいさつのあと。読み上げと GPU を分け合うので 1 つずつ）"""
        source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=200)
        try:
            await room.local_participant.publish_track(
                rtc.LocalAudioTrack.create_audio_track(TRACK, source),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        except Exception as e:   # 相づちが無くても、返事はする
            log.warning('相づちのトラックを出せない: %s', e)
            return
        self._source = source
        for path in sorted(THINK_DIR.glob('*.wav')):
            try:
                with wave.open(str(path)) as w:
                    if w.getnchannels() != 1 or w.getsampwidth() != 2:
                        raise ValueError('1 チャンネル・16 bit ではない')
                    self._think[path.stem] = self._fit(w.readframes(w.getnframes()), w.getframerate())
            except Exception as e:
                log.warning('考えるときの相づち %s を読めない: %s', path.name, e)
        t0 = time.perf_counter()
        async with aiohttp.ClientSession() as http:
            for text, length in HEARD.items():
                for _ in range(TRIES):
                    try:
                        pcm, sr = await emotion.synthesize(http, text, CAPTION, length)
                    except Exception as e:   # 相づちが無くても、返事はする
                        log.warning('相づち「%s」を読み上げられない: %s', text, e)
                        break
                    pcm = trim(pcm, sr)
                    seconds = len(pcm) / 2 / sr
                    if seconds <= MAX_SECONDS:
                        self._voices[text] = self._fit(pcm, sr)
                        break
                    log.info('相づち「%s」が %.2f 秒と長いので、読み上げ直す', text, seconds)
        log.info('相づちを用意した：聞いたとき %d 個（読み上げ %.1f 秒）、考えるとき %d 個',
                 len(self._voices), time.perf_counter() - t0, len(self._think))

    def _fit(self, pcm: bytes, sr: int) -> list[rtc.AudioFrame]:
        """声のトラックの音の形（サンプリング周波数・1 チャンネル・20 ms ずつ）にそろえる"""
        rate = self._source.sample_rate
        if sr != rate:
            resampler = rtc.AudioResampler(sr, rate, num_channels=1)
            out = [g for f in emotion.frames(pcm, sr) for g in resampler.push(f)] + list(resampler.flush())
            pcm = b''.join(bytes(f.data) for f in out)
        n = rate // 50 * 2
        pcm += bytes(-len(pcm) % n)
        return [rtc.AudioFrame(pcm[i:i + n], rate, 1, n // 2) for i in range(0, len(pcm), n)]

    def new_turn(self) -> None:
        """相手の発言が区切られた（その発言の文字起こしは、このあとに届く）"""
        self._question = False
        self._heard.clear()

    def heard(self, text: str) -> None:
        """相手の発言の文字起こし（届いていれば、質問かどうかで相づちを選ぶ）"""
        self._question = bool(QUESTION.search(text.strip()))
        self._heard.set()

    def play(self) -> None:
        """相づちを 1 つ流す（turns.py が、相手の発言への返事を頼むときに呼ぶ）"""
        if self._source is None or not (self._voices or self._think) or (self._task is not None and not self._task.done()):
            return
        self._task = asyncio.create_task(self._play())

    def nod(self) -> bool:
        """話している途中の息つぎに、聞いたときの相づちを 1 つ流す（文字起こしは待たない）。流したら True"""
        if self._source is None or not self._voices or (self._task is not None and not self._task.done()):
            return False
        self._task = asyncio.create_task(self._play(nod=True))
        return True

    def played_within(self, seconds: float) -> bool:
        """相づちを流してから seconds 以内か"""
        return self._played_at is not None and time.monotonic() - self._played_at < seconds

    async def _play(self, nod: bool = False) -> None:
        if not nod:
            try:
                await asyncio.wait_for(self._heard.wait(), TEXT_WAIT_SECONDS)
            except asyncio.TimeoutError:
                pass
        # 考えるときの相づちが無ければ、聞いたときの相づち
        voices = self._think if self._question and self._think and not nod else self._voices
        choices = [k for k in voices if word(k) != self._last] or list(voices)
        if not choices:
            return
        key = random.choice(choices)
        self._last = word(key)
        self._played_at = time.monotonic()
        log.info('相づち%s：%s', '（話の途中）' if nod else '', key)
        frames = voices[key]

        async def each():
            for f in frames:
                yield f
        # capture_frame は、音源にためた声が 0.2 秒を超えると待つので、流れる速さで入る
        async for f in self.volume.apply(each()):
            await self._source.capture_frame(f)

    async def wait(self) -> None:
        """流している相づちが鳴り終わるまで待つ（返事の声を重ねない。emotion.py）"""
        if self._task is not None and not self._task.done():
            await asyncio.wait({self._task})   # 止めた（取り消した）相づちでも、例外にしない
        if self._source is not None:
            await self._source.wait_for_playout()

    def stop(self) -> None:
        """相手が話し始めたら、流している相づちを止める"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            self._source.clear_queue()

    def strip(self, body: str) -> str:
        """相づちを流したすぐあとの返事なら、最初の文の頭の相づちを外す（全部が相づちなら、そのまま）"""
        if self._played_at is None or time.monotonic() - self._played_at > STRIP_SECONDS:
            return body
        self._played_at = None
        rest = LEADING.sub('', body, count=1)
        return rest if rest.strip() else body


def trim(pcm: bytes, sr: int) -> bytes:
    """前後の無音を除く（声の前後に 30 ms ずつ残す）"""
    x = np.frombuffer(pcm, '<i2').astype(np.float32) / 32768
    n = sr // 100
    frames = x[: len(x) // n * n].reshape(-1, n)
    if len(frames) == 0:
        return pcm
    loud = np.nonzero(20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9) > SILENCE_DB)[0]
    if len(loud) == 0:
        return pcm
    a, b = max(loud[0] - 3, 0) * n, min(loud[-1] + 4, len(frames)) * n
    return pcm[a * 2:b * 2]


def word(key: str) -> str:
    """相づちの言葉（考えるときの相づちのファイル名「0-えっと-C-1.0-1」なら「えっと」）"""
    parts = key.split('-')
    return parts[1] if len(parts) >= 5 else key
