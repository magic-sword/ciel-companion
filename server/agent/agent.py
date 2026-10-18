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
import json
import logging
import os

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext
from livekit.plugins import openai
from openai.types.realtime.audio_transcription import AudioTranscription
from openai.types.realtime.realtime_reasoning import RealtimeReasoning
from openai.types.realtime.realtime_audio_input_turn_detection import SemanticVad

import aizuchi
import emotion
import initiative
import irodori_tts
import minutes
import mode
import notes
import relationship
import speaker_store
import speakers
import tools
import touch
import turns
import voice_conversion
import volume
from persona import load_persona

load_dotenv()
logger = logging.getLogger('ciel-agent')

# 待機させておく子プロセスの数（既定は CPU の数 = 24 で多すぎる。会話は 1 人ずつなので 2 で足りる）
# 状態確認の HTTP の口（既定 8081）。試験用の会話サーバーを同じマシンで動かすときは別の番号にする（bench_latency.py）
server = AgentServer(num_idle_processes=2, port=int(os.environ.get('CIEL_AGENT_PORT', '8081')))
VOICE = os.environ.get('CIEL_VOICE', 'irodori')
# GPT-Live は聞きながら話す全二重なので、返事の作らせ方を変えない（話者の識別も使わない）
REALTIME = os.environ.get('CIEL_MODEL', 'realtime') != 'gpt-live'
# 話者の識別（speakers.py）は、文字から声を作る方式と Realtime API のときだけ
SPEAKERS = VOICE == 'irodori' and REALTIME
# Realtime API の雑音除去（make_model）
NOISE_REDUCTION = os.environ.get('CIEL_NOISE_REDUCTION', 'far_field')
# 話し終わりの判定の早さ（semantic_vad の eagerness：low・medium・high・auto）
EAGERNESS = os.environ.get('CIEL_EAGERNESS', 'medium')
# 返事の前に考える量（minimal・low・medium・high。空ならモデルの既定）
REASONING = os.environ.get('CIEL_REASONING', 'minimal')
# 返事の声ができるまでの相づち（aizuchi.py）。0 で流さない
AIZUCHI = VOICE == 'irodori' and os.environ.get('CIEL_AIZUCHI', '1') != '0'
# 相手が長く話している途中の息つぎにも相づちを打つか（turns.py）。0 で打たない
NOD = os.environ.get('CIEL_NOD', '1') != '0'
# 議事録を始めた・終えたときに、シエルに渡す 1 行（どう伝えるかは config/prompts/minutes_voice.md）
MINUTES_LINES = {minutes.STARTED: '[議事録：とり始めた]', minutes.ALREADY: '[議事録：もうとっている]',
                 minutes.FINISHED: '[議事録：まとめて送る]', minutes.NOT_RECORDING: '[議事録：とっていない]'}


def transcription(names: list[str]) -> AudioTranscription:
    """相手の発言の文字起こし（メモの元になる）。日本語と、よく出る名前のヒントを渡す。
    ヒントが無いと「シエル」が「CL」「チエル」「スチール」などになった（2026-10-16、合成音声で 3 文中 2 文。ヒントありは 3 文とも正しい）"""
    hint = '、'.join(dict.fromkeys(['シエル', *names]))[:400]
    return AudioTranscription(model='gpt-4o-mini-transcribe', language='ja',
                              prompt=f'AI キャラクター「シエル」との会話。出てくる名前：{hint}')


def make_model(names: list[str] | None = None):
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
        turn_detection=SemanticVad(type='semantic_vad', eagerness=EAGERNESS, create_response=False, interrupt_response=True),
        # 返事の前に考える量。既定のままだと毎回 70 トークンほど考えてから書き始め、0.6 秒ほど遅れた（2026-10-17）
        reasoning=RealtimeReasoning(effort=REASONING) if REASONING else None,
        # 相手の発言の文字起こし：日本語と、シエル・覚えている人の名前をヒントにする
        input_audio_transcription=transcription(names or []),
        # 雑音除去（生活音で「話し始めた」と判定され、シエルの話が止まるのを減らす）。
        # far_field … 少し離れた PC のマイク（既定）、near_field … ヘッドセット、off … 使わない
        input_audio_noise_reduction=None if NOISE_REDUCTION == 'off' else NOISE_REDUCTION,
    )


class Ciel(Agent):
    def __init__(self) -> None:
        persona = load_persona()
        self.persona = persona
        # 道具（tools/）は、会話モデルが必要なときに呼ぶ。使い方は config/prompts/ で教える
        super().__init__(instructions=self.instructions_for('normal', 'solo'), tools=tools.TOOLS)
        self.events = emotion.ExpressionEvents()
        self.volume = volume.VoiceVolume()   # 設定画面で選んだ声の大きさ（volume.py）
        self.aizuchi = aizuchi.Backchannel(self.volume)   # 返事の声ができるまでの相づち（aizuchi.py）

    def instructions_for(self, talk: str, presence: str) -> str:
        """会話のしかた（mode.py）ごとの指示。その場にいる人（presence_*.md、覚えていることの出し方）と、
        おしゃべり度（ひかえめ talk_quiet.md・おしゃべり talk_chatty.md。ふつうは足さない）を最後に足す。"""
        p = self.persona
        instructions = p.instructions + (p.emotion_instructions if VOICE == 'irodori' else '')
        # 画面のタッチへの反応（touch.py）
        instructions = instructions.rstrip('\n') + '\n\n' + p.touch_instructions
        if SPEAKERS:
            # 誰と話しているか（[発言者：…]）と、人についての道具の使い方（speakers.py、tools/people.py）
            instructions = instructions.rstrip('\n') + '\n\n' + p.speaker_instructions
        # 声で頼まれたときの議事録の道具と、始めた・終えたときの一言（tools/minutes.py、minutes.py）
        instructions = instructions.rstrip('\n') + '\n\n' + p.minutes_voice_instructions
        if SPEAKERS:
            presence_text = {'solo': p.presence_solo_instructions, 'close': p.presence_close_instructions,
                             'public': p.presence_public_instructions}[presence]
            instructions = instructions.rstrip('\n') + '\n\n' + presence_text
        talk_text = {'quiet': p.talk_quiet_instructions, 'chatty': p.talk_chatty_instructions}.get(talk)
        if talk_text:
            instructions = instructions.rstrip('\n') + '\n\n' + talk_text
        return instructions

    def tts_node(self, text, model_settings):
        # 1 文ずつ、感情の印に合わせた声で読み上げ、Unity へ表情を送る（emotion.py）。
        # ひかえめのときに黙ると決めた返事（[silent]）は読み上げない（mode.py）
        if VOICE == 'irodori':
            return self.volume.apply(emotion.tts_node(mode.drop_silent(text), self.events, self.aizuchi))
        return self.volume.apply(Agent.default.tts_node(self, text, model_settings))

    def transcription_node(self, text, model_settings):
        if VOICE == 'irodori':
            return emotion.transcription_node(mode.drop_silent(text))
        return Agent.default.transcription_node(self, text, model_settings)

    def realtime_audio_output_node(self, audio, model_settings):
        if VOICE == 'ciel':
            return self.volume.apply(voice_conversion.convert(audio))
        return self.volume.apply(Agent.default.realtime_audio_output_node(self, audio, model_settings))


# 名前を付けると、その名前で呼んだ部屋にだけ入る（試験用の会話サーバー。bench_latency.py）。本番は空のまま
@server.rtc_session(agent_name=os.environ.get('CIEL_AGENT_NAME', ''))
async def entrypoint(ctx: JobContext) -> None:
    logger.info('room=%s に入ります（声：%s）', ctx.room.name, VOICE)
    # 返事は turns.py が作らせるので、LiveKit の側でも自動で返事をしない（manual）
    # 話者の識別（speakers.py）。覚えている人は DB から読む（つなげなければ、この会話の間だけ覚える）
    store = await speaker_store.Store.open() if SPEAKERS else None
    book = speakers.SpeakerBook(store) if SPEAKERS else None
    if book is not None:
        await book.load()
    names = [k.name for k in book.known][:30] if book is not None else []   # 文字起こしのヒント（覚えている人の名前）
    session = AgentSession(llm=make_model(names), tts=irodori_tts.make() if VOICE == 'irodori' else None,
                           turn_detection='manual' if REALTIME else agents.NOT_GIVEN,
                           userdata=tools.State(book=book))   # 道具（tools/）から使う会話の状態
    agent = Ciel()
    tap = speakers.AudioTap()

    def on_track(track: rtc.Track, publication, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
            tap.attach(track)   # Unity のマイク（会議では、仮想ケーブルで届く会議の声）
    ctx.room.on('track_subscribed', on_track)
    # 会話のしかた（mode.py）。いまの答え方・覚えていることの出し方は、変わるたびに Unity へ知らせる
    style = mode.ConversationStyle(agent, agent.instructions_for, can_quiet=VOICE == 'irodori')
    style.publish = lambda msg: asyncio.create_task(ctx.room.local_participant.publish_data(
        json.dumps(msg), reliable=True, topic='ciel.event'))
    replies = turns.TurnReplies(session, book, tap, style, agent.persona.talk_quiet_turn_instructions,
                                agent.aizuchi if AIZUCHI else None)
    replies.nod = NOD
    # おしゃべりのとき、しばらく静かなら自分から話しかける（initiative.py）
    talker = initiative.Initiative(session, style, agent.persona.talk_chatty_nudge)
    session.on('user_state_changed', talker.on_user_state)
    session.on('agent_state_changed', talker.on_agent_state)
    if REALTIME:
        session.on('user_state_changed', replies.on_user_state)
        session.on('user_input_transcribed', replies.on_transcribed)   # 文字起こしの確定で返事を作らせる
        session.on('conversation_item_added', replies.on_item)   # 多人数で、シエルの質問への答えを待つ
    if SPEAKERS:
        asyncio.create_task(replies.load_encoder())

    # その人について覚えておくメモを、会話の裏で書く（notes.py。覚えている人で、お話を覚えることに同意した人だけ）
    note_taker = notes.NoteTaker(book, agent.persona.notes_instructions) if book is not None and store else None
    session.userdata.notes = note_taker   # 道具 remember_about_speaker が、覚えることを記録係に預ける
    # シエルがその人をどう思っているか（relationship.py）。会話の終わりに、この会話を振り返って書き直す
    relation_keeper = (relationship.RelationKeeper(book, note_taker, agent.persona.relationship_instructions)
                       if note_taker is not None else None)
    # 会議の議事録（minutes.py）。始めと終わりは、アプリのボタン・管理用のコマンド（ciel.minutes）と、声（道具 tools/minutes.py）から
    minute_taker = minutes.Minutes(book, agent.persona.minutes_instructions)
    session.userdata.minutes = minute_taker

    def on_minutes(what: str) -> None:
        # シエルに一言告げさせ（config/prompts/minutes_voice.md）、アプリのボタンの表示を合わせる
        session.generate_reply(instructions=MINUTES_LINES[what])
        msg = json.dumps({'v': 1, 'type': 'minutes.state', 'recording': minute_taker.recording})
        asyncio.create_task(ctx.room.local_participant.publish_data(msg, reliable=True, topic='ciel.event'))
    minute_taker.on_change = on_minutes
    takers = [t for t in (note_taker, minute_taker) if t is not None]
    if note_taker is not None:
        book.on_notes_consent = note_taker.on_consent   # 同意したら、同意の前に話したことも含めてすぐ書く
    if book is not None:
        def on_split(old, new) -> None:   # 人違いを直したら、その発言を分けた人の発言にする
            for t in takers:
                t.on_split(old, new)
        book.on_split = on_split
    # 文字起こしが確定するたびに、その発言の声で誰の発言かを決めてから、記録係・議事録の係に渡す（turns.py の speaker_of）。
    # 「最後に判定した人」を使うと、ほかの人の発言が前の人の発言になり、メモに混ざった（2026-10-18）
    pending_texts: set[asyncio.Task] = set()

    async def to_takers(text: str, segment) -> None:
        owner, sure = await replies.speaker_of(segment)
        for t in takers:
            t.on_user_text(text, owner, sure)

    def on_final_text(ev) -> None:
        if not ev.is_final:
            return
        segment = replies.take_segment()   # 文字起こしが届いた順に、発言の区間と組にする（ここで先に取る）
        if ev.transcript.strip():
            t = asyncio.create_task(to_takers(ev.transcript, segment))
            pending_texts.add(t)
            t.add_done_callback(pending_texts.discard)
    session.on('user_input_transcribed', on_final_text)
    session.on('conversation_item_added',
               lambda ev: [t.on_ciel_text(ev.item.text_content or '') for t in takers]
               if getattr(ev.item, 'role', None) == 'assistant' else None)

    async def close_store() -> None:
        await asyncio.gather(*pending_texts, return_exceptions=True)   # 話者を決めている途中の発言も渡してから
        await minute_taker.flush()   # 議事録をとっている途中なら、そこまでで下書きを送る
        if note_taker is not None:
            await note_taker.flush()   # 会話の終わりに、まだメモにしていない分を書く
        if relation_keeper is not None:
            await relation_keeper.flush()   # メモを書いたあとで、関係を書き直す
        if store is not None:
            await store.close()
    ctx.add_shutdown_callback(close_store)
    logger.info('persona_sha256=%s model=%s realtime_model=%s voice=%s',
                agent.persona.fingerprint, os.environ.get('CIEL_MODEL', 'realtime'),
                os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini')
                if os.environ.get('CIEL_MODEL', 'realtime') != 'gpt-live' else 'n/a', VOICE)
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=agent, record=False)
    # Unity で相手がシエルに触れたら、反応を話す（touch.py）。誰が触ったかは、声（話していた人）から推し量る
    toucher = touch.TouchReactions(session, book, style)
    replies.touch = toucher
    session.on('user_state_changed', toucher.on_user_state)
    ctx.room.on('data_received', toucher.on_data)
    # 会話のしかたの切り替え（mode.py。Unity が知らせる）
    ctx.room.on('data_received', style.on_data)
    # 議事録の始めと終わり（minutes.py。アプリのボタンと minutes_admin.py が送る）
    ctx.room.on('data_received', minute_taker.on_data)
    # シエルの声の大きさ（volume.py。アプリの設定画面が知らせる）
    ctx.room.on('data_received', agent.volume.on_data)
    await session.generate_reply(instructions=agent.persona.greeting)
    talker.start()
    if AIZUCHI:
        await agent.aizuchi.prepare(ctx.room)   # あいさつのあとに、相づちの声を読み上げておく


if __name__ == '__main__':
    agents.cli.run_app(server)
