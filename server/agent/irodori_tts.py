# -*- coding: utf-8 -*-
"""LiveKit Agents の TTS として、Irodori-TTS の読み上げサービス（../tts-irodori、同じマシンの HTTP）を使う。

会話モデルには文字だけを作らせ、その文字を 1 文ずつこのサービスでシエルの声にする。
1 文ずつに分けるのは StreamAdapter（日本語の 。！？ で区切る basic の文の区切り）。
"""
import asyncio
import hashlib
import logging
import os
import time
import uuid

import aiohttp
from livekit.agents import APIConnectionError, APIConnectOptions, get_job_context, tokenize, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

URL = os.environ.get('CIEL_TTS_URL', 'http://127.0.0.1:8766/synthesize')
SESSION_ID = uuid.uuid4().hex  # A job process belongs to one conversation; no personal identifiers.
log = logging.getLogger('ciel-agent.tts')


async def request_audio(http: aiohttp.ClientSession, body: dict, *, session_id=None) -> tuple[bytes, int]:
    if session_id is None:
        ctx = get_job_context(required=False)
        session_id = hashlib.sha256(ctx.job.id.encode()).hexdigest()[:24] if ctx else SESSION_ID
    request_id = uuid.uuid4().hex
    complete = False
    started = time.monotonic()
    try:
        async with http.post(URL, json={**body, 'session_id': session_id, 'request_id': request_id},
                             timeout=aiohttp.ClientTimeout(total=30)) as r:
            r.raise_for_status()
            pcm = await r.read()
            complete = True
            log.info('tts session=%s request=%s queue_ms=%s total_ms=%.0f', session_id, request_id,
                     r.headers.get('X-Queue-Ms', 'unknown'), (time.monotonic() - started) * 1000)
            return pcm, int(r.headers.get('X-Sample-Rate', '48000'))
    finally:
        if not complete:
            # Use a separate short-lived connection: the interrupted request may have closed its session.
            async def cancel():
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as control:
                    async with control.delete(URL + '/' + request_id, params={'session_id': session_id}):
                        pass
            try:
                await asyncio.shield(cancel())
            except (Exception, asyncio.CancelledError):
                pass  # The server also discards jobs that expire before starting.


class IrodoriTTS(tts.TTS):
    def __init__(self, sample_rate: int = 48000) -> None:
        super().__init__(capabilities=tts.TTSCapabilities(streaming=False), sample_rate=sample_rate, num_channels=1)
        self._session: aiohttp.ClientSession | None = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.ChunkedStream:
        return _Chunked(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()


class _Chunked(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        t: IrodoriTTS = self._tts  # type: ignore[assignment]
        try:
            pcm, sr = await request_audio(t._http(), {'text': self._input_text})
            output_emitter.initialize(request_id=str(uuid.uuid4()), sample_rate=sr, num_channels=1,
                                      mime_type='audio/pcm')
            output_emitter.push(pcm)
            output_emitter.flush()
        except aiohttp.ClientError as e:
            raise APIConnectionError(f'Irodori-TTS の読み上げサービスにつながらない: {e}') from e


def make() -> tts.TTS:
    """1 文ずつ読み上げる TTS。文が短すぎると不自然なので 6 字以上をひとまとめにし、区切りを待ちすぎない。"""
    return tts.StreamAdapter(
        tts=IrodoriTTS(),
        sentence_tokenizer=tokenize.basic.SentenceTokenizer(language='japanese', min_sentence_len=6, stream_context_len=2),
    )
