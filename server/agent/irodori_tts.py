# -*- coding: utf-8 -*-
"""LiveKit Agents の TTS として、Irodori-TTS の読み上げサービス（../tts-irodori、同じマシンの HTTP）を使う。

会話モデルには文字だけを作らせ、その文字を 1 文ずつこのサービスでシエルの声にする。
1 文ずつに分けるのは StreamAdapter（日本語の 。！？ で区切る basic の文の区切り）。
"""
import os
import uuid

import aiohttp
from livekit.agents import APIConnectionError, APIConnectOptions, tokenize, tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

URL = os.environ.get('CIEL_TTS_URL', 'http://127.0.0.1:8766/synthesize')


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
            async with t._http().post(URL, json={'text': self._input_text},
                                      timeout=aiohttp.ClientTimeout(total=30)) as r:
                r.raise_for_status()
                sr = int(r.headers.get('X-Sample-Rate', t.sample_rate))
                output_emitter.initialize(request_id=str(uuid.uuid4()), sample_rate=sr, num_channels=1,
                                          mime_type='audio/pcm')
                async for chunk in r.content.iter_chunked(8192):
                    output_emitter.push(chunk)
                output_emitter.flush()
        except aiohttp.ClientError as e:
            raise APIConnectionError(f'Irodori-TTS の読み上げサービスにつながらない: {e}') from e


def make() -> tts.TTS:
    """1 文ずつ読み上げる TTS。文が短すぎると不自然なので 6 字以上をひとまとめにし、区切りを待ちすぎない。"""
    return tts.StreamAdapter(
        tts=IrodoriTTS(),
        sentence_tokenizer=tokenize.basic.SentenceTokenizer(language='japanese', min_sentence_len=6, stream_context_len=2),
    )
