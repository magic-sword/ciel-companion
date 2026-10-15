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
import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import openai
from openai.types.realtime.realtime_audio_input_turn_detection import SemanticVad

import emotion
import irodori_tts
import mode
import notes
import speaker_store
import speakers
import tools
import touch
import turns
import voice_conversion
from persona import load_persona

load_dotenv()
logger = logging.getLogger('ciel-agent')

# 待機させておく子プロセスの数（既定は CPU の数 = 24 で多すぎる。会話は 1 人ずつなので 2 で足りる）
server = AgentServer(num_idle_processes=2)
VOICE = os.environ.get('CIEL_VOICE', 'irodori')
# GPT-Live は聞きながら話す全二重なので、返事の作らせ方を変えない（話者の識別も使わない）
REALTIME = os.environ.get('CIEL_MODEL', 'realtime') != 'gpt-live'
# 話者の識別（speakers.py）は、文字から声を作る方式と Realtime API のときだけ
SPEAKERS = VOICE == 'irodori' and REALTIME


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
        # 話し終わりの判定と割り込みは今までどおり会話モデルの側（LiveKit の既定と同じ semantic_vad）。
        # 返事は自動で作らせず、turns.py が作らせる（多人数のとき、話者の 1 行を先に足すため）
        turn_detection=SemanticVad(type='semantic_vad', eagerness='medium', create_response=False, interrupt_response=True),
    )


class Ciel(Agent):
    def __init__(self) -> None:
        persona = load_persona()
        self.persona = persona
        # 道具（tools/）は、会話モデルが必要なときに呼ぶ。使い方は config/prompts/ で教える
        super().__init__(instructions=self.instructions_for('solo'), tools=tools.TOOLS)
        self.events = emotion.ExpressionEvents()

    def instructions_for(self, mode: str) -> str:
        """モード（mode.py）ごとの指示。group は多人数での答え方（config/prompts/group.md）を最後に足す。"""
        p = self.persona
        instructions = p.instructions + (p.emotion_instructions if VOICE == 'irodori' else '')
        # 画面のタッチへの反応（touch.py）
        instructions = instructions.rstrip('\n') + '\n\n' + p.touch_instructions
        if SPEAKERS:
            # 誰と話しているか（[発言者：…]）と、人についての道具の使い方（speakers.py、tools/people.py）
            instructions = instructions.rstrip('\n') + '\n\n' + p.speaker_instructions
        if mode == 'group':
            instructions = instructions.rstrip('\n') + '\n\n' + p.group_instructions
        return instructions

    def tts_node(self, text, model_settings):
        # 1 文ずつ、感情の印に合わせた声で読み上げ、Unity へ表情を送る（emotion.py）。
        # 多人数で黙ると決めた返事（[silent]）は読み上げない（mode.py）
        if VOICE == 'irodori':
            return emotion.tts_node(mode.drop_silent(text), self.events)
        return Agent.default.tts_node(self, text, model_settings)

    def transcription_node(self, text, model_settings):
        if VOICE == 'irodori':
            return emotion.transcription_node(mode.drop_silent(text))
        return Agent.default.transcription_node(self, text, model_settings)

    def realtime_audio_output_node(self, audio, model_settings):
        if VOICE == 'ciel':
            return voice_conversion.convert(audio)
        return Agent.default.realtime_audio_output_node(self, audio, model_settings)


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    logger.info('room=%s に入ります（声：%s）', ctx.room.name, VOICE)
    # 返事は turns.py が作らせるので、LiveKit の側でも自動で返事をしない（manual）
    # 話者の識別（speakers.py）。覚えている人は DB から読む（つなげなければ、この会話の間だけ覚える）
    store = await speaker_store.Store.open() if SPEAKERS else None
    book = speakers.SpeakerBook(store) if SPEAKERS else None
    if book is not None:
        await book.load()
    session = AgentSession(llm=make_model(), tts=irodori_tts.make() if VOICE == 'irodori' else None,
                           turn_detection='manual' if REALTIME else agents.NOT_GIVEN,
                           userdata=tools.State(book=book))   # 道具（tools/）から使う会話の状態
    agent = Ciel()
    tap = speakers.AudioTap()

    def on_track(track: rtc.Track, publication, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
            tap.attach(track)   # Unity のマイク（会議では、仮想ケーブルで届く会議の声）
    ctx.room.on('track_subscribed', on_track)
    switch = mode.ModeSwitch(agent, agent.instructions_for, can_group=VOICE == 'irodori')
    replies = turns.TurnReplies(session, book, tap, switch)
    if REALTIME:
        session.on('user_state_changed', replies.on_user_state)
    if SPEAKERS:
        asyncio.create_task(replies.load_encoder())

    # その人について覚えておくメモを、会話の裏で書く（notes.py。覚えている人で、お話を覚えることに同意した人だけ）
    note_taker = notes.NoteTaker(book, agent.persona.notes_instructions) if book is not None and store else None
    session.userdata.notes = note_taker   # 道具 remember_about_speaker が、覚えることを記録係に預ける
    if note_taker is not None:
        book.on_notes_consent = note_taker.on_consent   # 同意したら、同意の前に話したことも含めてすぐ書く
        book.on_split = note_taker.on_split             # 人違いを直したら、その発言を分けた人の発言にする
        session.on('user_input_transcribed',
                   lambda ev: note_taker.on_user_text(ev.transcript) if ev.is_final else None)
        session.on('conversation_item_added',
                   lambda ev: note_taker.on_ciel_text(ev.item.text_content or '')
                   if getattr(ev.item, 'role', None) == 'assistant' else None)

    async def close_store() -> None:
        if note_taker is not None:
            await note_taker.flush()   # 会話の終わりに、まだメモにしていない分を書く
        if store is not None:
            await store.close()
    ctx.add_shutdown_callback(close_store)
    logger.info('persona_sha256=%s model=%s realtime_model=%s voice=%s',
                agent.persona.fingerprint, os.environ.get('CIEL_MODEL', 'realtime'),
                os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini')
                if os.environ.get('CIEL_MODEL', 'realtime') != 'gpt-live' else 'n/a', VOICE)
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=agent, record=False)
    # Unity で相手がシエルに触れたら、反応を話す（touch.py）
    ctx.room.on('data_received', touch.TouchReactions(session).on_data)
    # 2 人・多人数の会話の切り替え（mode.py。Unity が知らせる）
    ctx.room.on('data_received', switch.on_data)
    await session.generate_reply(instructions=agent.persona.greeting)


if __name__ == '__main__':
    agents.cli.run_app(server)
