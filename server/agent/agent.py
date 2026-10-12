# -*- coding: utf-8 -*-
"""シエルの会話サーバー（LiveKit Agents）。

LiveKit Cloud のルームにアプリが入ると、このプログラムが呼ばれてルームに入り、
アプリのマイク音声を OpenAI の音声会話モデルへ送り、シエルの声で返事をアプリへ返す。

シエルの声の作り方は環境変数 CIEL_VOICE で切り替える：
  irodori … 会話モデルには文字だけを作らせ、Irodori-TTS（server/tts-irodori）で 1 文ずつ読み上げる（既定）
  ciel    … 会話モデルの声を、声質変換サービス（server/voice-conversion、Seed-VC）で変換する
  openai  … 会話モデルの声のまま（比べるとき）

会話モデルは環境変数 CIEL_MODEL で切り替える：
  realtime（既定）… OpenAI Realtime API（gpt-realtime 系）
  gpt-live        … GPT-Live（全二重。利用権限が要る。irodori とは組み合わせない）

実行（開発）  python -m livekit.agents start agent.py --dev
必要な環境変数は .env.example を参照（秘密情報は .env に書き、Git に入れない）。
"""
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import openai

import emotion
import irodori_tts
import voice_conversion
from persona import EMOTION_INSTRUCTIONS, GREETING, INSTRUCTIONS

load_dotenv()
logger = logging.getLogger('ciel-agent')

# 待機させておく子プロセスの数（既定は CPU の数 = 24 で多すぎる。会話は 1 人ずつなので 2 で足りる）
server = AgentServer(num_idle_processes=2)
VOICE = os.environ.get('CIEL_VOICE', 'irodori')


def make_model():
    kind = os.environ.get('CIEL_MODEL', 'realtime')
    voice = os.environ.get('CIEL_OPENAI_VOICE', 'marin')
    if kind == 'gpt-live':
        return openai.realtime.GPTLiveModel(voice=voice)
    return openai.realtime.RealtimeModel(
        model=os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini'),
        voice=voice,
        # irodori：声は Irodori-TTS で作るので、会話モデルには文字だけを作らせる（音声の出力の料金もかからない）
        modalities=['text'] if VOICE == 'irodori' else ['text', 'audio'],
    )


class Ciel(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS + (EMOTION_INSTRUCTIONS if VOICE == 'irodori' else ''))
        self.events = emotion.ExpressionEvents()

    def tts_node(self, text, model_settings):
        # 1 文ずつ、感情の印に合わせた声で読み上げ、Unity へ表情を送る（emotion.py）
        if VOICE == 'irodori':
            return emotion.tts_node(text, self.events)
        return Agent.default.tts_node(self, text, model_settings)

    def transcription_node(self, text, model_settings):
        if VOICE == 'irodori':
            return emotion.transcription_node(text)
        return Agent.default.transcription_node(self, text, model_settings)

    def realtime_audio_output_node(self, audio, model_settings):
        if VOICE == 'ciel':
            return voice_conversion.convert(audio)
        return Agent.default.realtime_audio_output_node(self, audio, model_settings)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info('room=%s に入ります（声：%s）', ctx.room.name, VOICE)
    session = AgentSession(llm=make_model(), tts=irodori_tts.make() if VOICE == 'irodori' else None)
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=Ciel(), record=False)
    await session.generate_reply(instructions=GREETING)


if __name__ == '__main__':
    agents.cli.run_app(server)
