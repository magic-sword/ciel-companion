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
import debug_log
import emotion
import initiative
import interruptions
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
import usage
import voice_conversion
import volume
from conversation import Conversation
from conversation_recording import ConversationRecorder
from web_research import WebResearcher
from persona import load_persona

load_dotenv()
logger = logging.getLogger('ciel-agent')

# 待機させておく子プロセスの数（既定は CPU の数 = 24 で多すぎる。会話は 1 人ずつなので 2 で足りる）
# 状態確認の HTTP の口（既定 8081）。試験用の会話サーバーを同じマシンで動かすときは別の番号にする（bench_latency.py）
# 会話が終わってから後片付け（議事録の清書と送信・メモ・関係の書き直し）を待つ秒数。既定の 10 秒では、
# 議事録の清書（11〜18 秒）の途中で子プロセスが止められ、下書きもメモも失われた（2026-10-23）。
# 議事録は minutes.FLUSH_SECONDS で打ち切って、間に合わなければライブの一覧で下書きにする
server = AgentServer(num_idle_processes=2, port=int(os.environ.get('CIEL_AGENT_PORT', '8081')),
                     shutdown_process_timeout=90.0)
VOICE = os.environ.get('CIEL_VOICE', 'irodori')
# 会話モデル（realtime・gpt-live）と、realtime のときのモデル名
MODEL = os.environ.get('CIEL_MODEL', 'realtime')
REALTIME_MODEL = os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini')
# GPT-Live は聞きながら話す全二重なので、返事の作らせ方を変えない（話者の識別も使わない）
REALTIME = MODEL != 'gpt-live'
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
# シエルが話している途中の短い声（咳・相づち）では止めない（interruptions.py。CIEL_INTERRUPT_SECONDS=0 で以前のやり方）
INTERRUPT_GATE = REALTIME and interruptions.CONFIRM_SECONDS > 0
# 議事録を始めた・終えたときに、シエルに渡す 1 行（どう伝えるかは config/prompts/minutes_voice.md）
MINUTES_LINES = {minutes.STARTED: '[議事録：とり始めた]', minutes.ALREADY: '[議事録：もうとっている]',
                 minutes.FINISHED: '[議事録：まとめて送る]', minutes.NOT_RECORDING: '[議事録：とっていない]',
                 minutes.PAST_QUEUED: '[議事録：ここまでをまとめて送る]',
                 minutes.PAST_PARTIAL: '[議事録：残っている範囲をまとめて送る]',
                 minutes.STARTED_EARLIER: '[議事録：さかのぼってとり始めた]',
                 minutes.STARTED_PARTIAL: '[議事録：残っている範囲からとり始めた]'}


def transcription(names: list[str]) -> AudioTranscription:
    """相手の発言の文字起こし（メモの元になる）。日本語と、よく出る名前のヒントを渡す。
    ヒントが無いと「シエル」が「CL」「チエル」「スチール」などになった（2026-10-16、合成音声で 3 文中 2 文。ヒントありは 3 文とも正しい）"""
    hint = '、'.join(dict.fromkeys(['シエル', *names]))[:400]
    return AudioTranscription(model='gpt-4o-mini-transcribe', language='ja',
                              prompt=f'AI キャラクター「シエル」との会話。出てくる名前：{hint}')


def make_model(names: list[str] | None = None):
    voice = os.environ.get('CIEL_OPENAI_VOICE', 'marin')
    if not REALTIME:
        return openai.realtime.GPTLiveModel(voice=voice)
    return openai.realtime.RealtimeModel(
        model=REALTIME_MODEL,
        voice=voice,
        # irodori：声は Irodori-TTS で作るので、会話モデルには文字だけを作らせる（音声の出力の料金もかからない）
        modalities=['text'] if VOICE == 'irodori' else ['text', 'audio'],
        # 話し終わりの判定と割り込みは今までどおり会話モデルの側（LiveKit の既定と同じ semantic_vad）。
        # 返事は自動で作らせず、turns.py が作らせる（多人数のとき、話者の 1 行を先に足すため）
        turn_detection=SemanticVad(type='semantic_vad', eagerness=EAGERNESS, create_response=False,
                                  # 話し始めで返事を取り消さない。止めるかは interruptions.py が決める
                                  interrupt_response=not INTERRUPT_GATE),
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
        parts = [p.instructions + (p.emotion_instructions if VOICE == 'irodori' else ''),
                 p.touch_instructions]   # 画面のタッチへの反応（touch.py）
        if SPEAKERS:
            # 誰と話しているか（[発言者：…]）と、人についての道具の使い方（speakers.py、tools/people.py）
            parts.append(p.speaker_instructions)
        # 声で頼まれたときの議事録の道具と、始めた・終えたときの一言（tools/minutes.py、minutes.py）
        parts += [p.minutes_voice_instructions, p.conversation_instructions, p.research_voice_instructions,
                  p.inner_thoughts_voice_instructions]
        if SPEAKERS:
            parts.append({'solo': p.presence_solo_instructions, 'close': p.presence_close_instructions,
                          'public': p.presence_public_instructions}[presence])
        talk_text = {'quiet': p.talk_quiet_instructions, 'chatty': p.talk_chatty_instructions}.get(talk)
        if talk_text:
            parts.append(talk_text)
        # 1 つずつ、前の末尾の改行を落として空行 1 つでつなぐ（最後の本文の末尾はそのまま）
        instructions = parts[0]
        for part in parts[1:]:
            instructions = instructions.rstrip('\n') + '\n\n' + part
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
    # デバッグ用の会話ログ（debug_log.py）。ふだんは残さない。入れているときだけ、この会話のファイルを作る
    debug_log.start(ctx.room.name, model=MODEL, realtime_model=REALTIME_MODEL if REALTIME else None, voice=VOICE)
    # 返事は turns.py が作らせるので、LiveKit の側でも自動で返事をしない（manual）
    # 話者の識別（speakers.py）。覚えている人は DB から読む（つなげなければ、この会話の間だけ覚える）
    store = await speaker_store.Store.open() if SPEAKERS else None
    book = speakers.SpeakerBook(store) if SPEAKERS else None
    if book is not None:
        await book.load()
    names = [k.name for k in book.known][:30] if book is not None else []   # 文字起こしのヒント（覚えている人の名前）
    session = AgentSession(llm=make_model(names), tts=irodori_tts.make() if VOICE == 'irodori' else None,
                           turn_detection='manual' if REALTIME else agents.NOT_GIVEN,
                           # 読み上げる前の文字の変換は、絵文字を外すだけにする。既定の filter_markdown は、返事の頭の
                           # 感情の印「[happy]」をリンクの書きかけとみなし、返事を最後まで書き終えるまで読み上げに渡さなかった
                           # （2026-10-22、bench_latency.py。印は emotion.py が読み取って外す）
                           tts_text_transforms=['filter_emoji'],
                           userdata=tools.State(book=book))   # 道具（tools/）から使う会話の状態
    agent = Ciel()
    tap = speakers.AudioTap()
    # 返事ごとのトークン数（usage.py）。指示を短くしたときの比べる基準
    usage_log = usage.UsageLog()
    session.on('session_usage_updated', usage_log.on_usage)
    debug_log.attach(session, ctx.room, agent)

    def on_track(track: rtc.Track, publication, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
            tap.attach(track)   # Unity のマイク（会議では、仮想ケーブルで届く会議の声）
    ctx.room.on('track_subscribed', on_track)
    # 会話のしかた（mode.py）。いまの答え方・覚えていることの出し方は、変わるたびに Unity へ知らせる
    style = mode.ConversationStyle(agent, agent.instructions_for, can_quiet=VOICE == 'irodori')
    style.publish = lambda msg: asyncio.create_task(ctx.room.local_participant.publish_data(
        json.dumps(msg), reliable=True, topic='ciel.event'))
    history = Conversation()
    session.userdata.history = history
    # 会話のまとめ（議事録など。minutes.py）。始めと終わりは、アプリのボタン・管理用のコマンド（ciel.minutes）と、声（道具 tools/minutes.py）から
    minute_taker = minutes.Minutes(book, agent.persona.minutes_instructions, history,
                                   agent.persona.minutes_live_instructions)
    session.userdata.minutes = minute_taker
    summary_seq = 0

    async def send(topic: str, *messages: dict) -> None:
        # アプリへの知らせ。会話が終わって部屋が閉じたあと（議事録の清書の結果など）は送れないので、捨てる
        try:
            for msg in messages:
                await ctx.room.local_participant.publish_data(
                    json.dumps(msg, ensure_ascii=False), reliable=True, topic=topic)
        except Exception as e:
            logger.info('アプリへ送れない（%s）: %s', topic, type(e).__name__)

    def publish_summary(state) -> None:
        # まとめの中身は大きいので、分けて送る（アプリが seq ごとにつなぐ）
        nonlocal summary_seq
        summary_seq += 1
        asyncio.create_task(send('ciel.summary', *minutes.packets(state, summary_seq)))
    minute_taker.on_state = publish_summary
    minute_taker.on_progress = lambda msg: asyncio.create_task(send('ciel.event', msg))
    replies = turns.TurnReplies(session, book, tap, style, agent.persona.talk_quiet_turn_instructions,
                                agent.aizuchi if AIZUCHI else None, history=history, minutes=minute_taker, nod=NOD)
    async def publish_research(packet):
        await ctx.room.local_participant.publish_data(
            json.dumps(packet, ensure_ascii=False), reliable=True, topic='ciel.research')
    researcher = WebResearcher(history, agent.persona.research_instructions, publish_research)
    session.userdata.researcher = researcher
    # シエルの内なる考え：会話の裏で考えを作り、話したい気持ちが強い考えを、会話が途切れたときに話す（initiative.py）
    talker = initiative.Initiative(session, style, agent.persona.talk_chatty_nudge, history=history,
                                   instructions=agent.persona.inner_thoughts_instructions,
                                   correction_nudge=agent.persona.talk_correction_nudge,
                                   state_header=agent.persona.talk_inner_state_instructions,
                                   memories=lambda: book.last.notes() if book is not None and book.last is not None
                                   and book.last_sure and style.presence in ('solo', 'close') else [])
    replies.initiative = talker   # 相手への返事に、話したかった考えを添える
    session.userdata.initiative = talker   # 道具 read_inner_thoughts・keep_thought が、心の中を読む・預ける
    session.on('user_state_changed', talker.on_user_state)
    session.on('agent_state_changed', talker.on_agent_state)
    if REALTIME:
        session.on('user_state_changed', replies.on_user_state)
        session.on('user_input_transcribed', replies.on_transcribed)   # 文字起こしの確定で返事を作らせる
        session.on('conversation_item_added', replies.on_item)   # 多人数で、シエルの質問への答えを待つ
    if SPEAKERS:
        asyncio.create_task(replies.load_encoder())

    # その人について覚えておくメモを、会話の裏で書く（notes.py。覚えている人で、お話を覚えることに同意した人だけ）
    note_taker = notes.NoteTaker(book, agent.persona.notes_instructions, history) if book is not None and store else None
    session.userdata.notes = note_taker   # 道具 remember_about_speaker が、覚えることを記録係に預ける
    # シエルがその人をどう思っているか（relationship.py）。会話の終わりに、この会話を振り返って書き直す
    relation_keeper = (relationship.RelationKeeper(book, note_taker, agent.persona.relationship_instructions, history)
                       if note_taker is not None else None)

    def on_minutes(what: str) -> None:
        # シエルに一言告げさせ（config/prompts/minutes_voice.md）、アプリのボタンの表示を合わせる
        session.generate_reply(instructions=MINUTES_LINES[what] + '\n\n' + minute_taker.context())
        msg = json.dumps({'v': 1, 'type': 'minutes.state', 'recording': minute_taker.recording})
        asyncio.create_task(ctx.room.local_participant.publish_data(msg, reliable=True, topic='ciel.event'))
    minute_taker.on_change = on_minutes
    if note_taker is not None:
        book.on_notes_consent = note_taker.on_consent   # 同意したら、同意の前に話したことも含めてすぐ書く
    if book is not None:
        book.on_split = history.on_split
        book.on_merge = history.on_merge
        # アプリの参加者パネル（speakers.py の state）。名簿・最後に話した人が変わるたびに知らせる
        book.on_change = lambda state: asyncio.create_task(send('ciel.event', state))
    # 書き起こし・発言時刻・その区間の話者を共通履歴へ一度だけ記録する。
    recorder = ConversationRecorder(history, replies, note_taker)
    session.on('user_input_transcribed', recorder.on_transcribed)
    session.on('conversation_item_added', recorder.on_item)

    async def close_store() -> None:
        usage_log.summary()
        debug_log.record('end')
        await recorder.flush()   # 話者を決めている途中の発言も渡してから
        await researcher.close()
        async def memories() -> None:
            if note_taker is not None:
                await note_taker.flush()   # 会話の終わりに、まだメモにしていない分を書く
            if relation_keeper is not None:
                await relation_keeper.flush()   # メモを書いたあとで、関係を書き直す
        # 議事録（とっている途中なら、そこまでで下書きを送る）とメモは別々なので、並べて待つ（片方の失敗で、もう片方を止めない）
        for result in await asyncio.gather(minute_taker.flush(), memories(), return_exceptions=True):
            if isinstance(result, BaseException):
                logger.warning('会話の後片付けに失敗 error=%s', type(result).__name__)
        if store is not None:
            await store.close()
    ctx.add_shutdown_callback(close_store)
    logger.info('persona_sha256=%s model=%s realtime_model=%s voice=%s',
                agent.persona.fingerprint, MODEL, REALTIME_MODEL if REALTIME else 'n/a', VOICE)
    logger.info('指示 %d 字・道具 %d 個', len(agent.instructions), len(agent.tools))
    debug_log.record('settings', persona_sha256=agent.persona.fingerprint, instructions_chars=len(agent.instructions),
                     tools=[getattr(t, 'id', str(t)) for t in agent.tools])
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=agent, record=False)
    # アプリの「まとめをとる」で選べるテンプレート（minutes.py）
    await ctx.room.local_participant.publish_data(
        json.dumps(minute_taker.templates_event(), ensure_ascii=False), reliable=True, topic='ciel.event')
    # Unity で相手がシエルに触れたら、反応を話す（touch.py）。誰が触ったかは、声（話していた人）から推し量る
    toucher = touch.TouchReactions(session, book, style)
    replies.touch = toucher
    # シエルが話している途中の短い声で、話を止めない（interruptions.py）
    if INTERRUPT_GATE:
        gate = interruptions.InterruptionGate(session, tap)
        if gate.install():
            replies.overlap = gate
        else:   # LiveKit の中が想定と違う。LiveKit が今までどおり話し始めた瞬間に止める
            logger.warning('中断の差し替えができなかった（今までどおり、話し始めた瞬間に止める）')
    session.on('user_state_changed', toucher.on_user_state)
    ctx.room.on('data_received', toucher.on_data)
    # 会話のしかたの切り替え（mode.py。Unity が知らせる）
    ctx.room.on('data_received', style.on_data)
    # 議事録の始めと終わり（minutes.py。アプリのボタンと minutes_admin.py が送る）
    ctx.room.on('data_received', minute_taker.on_data)
    # 参加者パネルからの名前の直し（speakers.py。この会話の間だけ）
    if book is not None:
        ctx.room.on('data_received', book.on_data)
        book.notify()
    # シエルの声の大きさ（volume.py。アプリの設定画面が知らせる）
    ctx.room.on('data_received', agent.volume.on_data)
    await session.generate_reply(instructions=agent.persona.greeting)
    talker.start()
    if AIZUCHI:
        await agent.aizuchi.prepare(ctx.room)   # あいさつのあとに、相づちの声を読み上げておく


if __name__ == '__main__':
    agents.cli.run_app(server)
