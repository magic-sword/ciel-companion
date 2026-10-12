# -*- coding: utf-8 -*-
"""シエルの会話サーバー（LiveKit Agents）。

LiveKit Cloud のルームにアプリが入ると、このプログラムが呼ばれてルームに入り、
アプリのマイク音声を OpenAI の音声会話モデルへ送り、返ってきた声をアプリへ返す。

フェーズ1（今）：OpenAI の既定の声のまま返す。
フェーズ2：返ってきた声を Seed-VC でシエルの声へ変換してから返す（voice_conversion.py、未実装）。

会話モデルは環境変数 CIEL_MODEL で切り替える：
  realtime（既定）… OpenAI Realtime API（gpt-realtime 系）
  gpt-live        … GPT-Live（全二重。利用権限が要る）

実行（開発）  python -m livekit.agents start agent.py --dev
必要な環境変数は .env.example を参照（秘密情報は .env に書き、Git に入れない）。
"""
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import openai

from persona import INSTRUCTIONS, GREETING

load_dotenv()
logger = logging.getLogger('ciel-agent')

server = AgentServer()


def make_model():
    kind = os.environ.get('CIEL_MODEL', 'realtime')
    voice = os.environ.get('CIEL_OPENAI_VOICE', 'marin')
    if kind == 'gpt-live':
        return openai.realtime.GPTLiveModel(voice=voice)
    return openai.realtime.RealtimeModel(
        model=os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini'),
        voice=voice,
    )


class Ciel(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info('room=%s に入ります', ctx.room.name)
    session = AgentSession(llm=make_model())
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=Ciel(), record=False)
    await session.generate_reply(instructions=GREETING)


if __name__ == '__main__':
    agents.cli.run_app(server)
