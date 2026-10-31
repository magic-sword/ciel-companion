# -*- coding: utf-8 -*-
"""シエルの会話サーバー（LiveKit Agents）。

LiveKit Cloud のルームにアプリが入ると、このプログラムが呼ばれてルームに入り、
アプリのマイク音声を OpenAI の音声会話モデルへ送り、シエルの声で返事をアプリへ返す。

シエルの声の作り方は環境変数 CIEL_VOICE で切り替える：
  irodori … 会話モデルには文字だけを作らせ、Irodori-TTS（server/tts-irodori）で 1 文ずつ読み上げる（既定）
  ciel    … 会話モデルの声を、声質変換サービス（server/voice-conversion、Seed-VC）で変換する
  openai  … 会話モデルの声のまま（比べるとき）

会話モデルは環境変数 CIEL_MODEL で切り替える：
  realtime（コードの既定）… OpenAI Realtime API（gpt-realtime 系）。2026-10-31 までの本番
  pipeline        … 音声検出 1 つ（silero）→ 話している途中から出る文字起こし → 区切りのモデル → 小脳と心（mind.py）
                    → Irodori。返事のたびに会話の記録から文脈を作る。本番・開発用の Compose はこれ
                    （仕組みは docs/conversation-pipeline-ja.md）
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
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, StopResponse, inference
from livekit.plugins import openai
from openai.types.realtime.audio_transcription import AudioTranscription
from openai.types.realtime.realtime_reasoning import RealtimeReasoning
from openai.types.realtime.realtime_audio_input_turn_detection import SemanticVad

import aizuchi
import board
import clock
import curiosity
import debug_log
import emotion
import initiative
import interruptions
import listener
import irodori_tts
import mind
import minutes
import mode
import models
import mouth
import notes
import relationship
import singing
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
# 会話モデル（realtime・pipeline・gpt-live）と、realtime のときのモデル名
MODEL = os.environ.get('CIEL_MODEL', 'realtime')
REALTIME_MODEL = os.environ.get('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini')
# GPT-Live は聞きながら話す全二重なので、返事の作らせ方を変えない（話者の識別も使わない）
REALTIME = MODEL == 'realtime'
# 文字起こし → 心 → 読み上げの組み立て。声は Irodori で作るので、irodori のときだけ
PIPELINE = MODEL == 'pipeline' and VOICE == 'irodori'
# 心の考える量（pipeline。none・minimal・low…）
MIND_REASONING = os.environ.get('CIEL_MIND_REASONING', 'none')
# 話し終えたと決めるまでの最短・最長の待ち（pipeline。秒）
# 最短 0.4 秒では、話の途中の 0.6 秒の息つぎで返事を始めては止められ、「わ」「は」だけが流れた（2026-10-30）。
# 話し方に合わせて待ちを変える（dynamic：その人の話の途中の間の長さを覚える）
ENDPOINT_MODE = os.environ.get('CIEL_ENDPOINT_MODE', 'dynamic')
ENDPOINT_MIN = float(os.environ.get('CIEL_ENDPOINT_MIN', '0.6'))
ENDPOINT_MAX = float(os.environ.get('CIEL_ENDPOINT_MAX', '1.5'))
# 返事を作る前に、聞く係が頼みを確かめ終えるのを待つ上限（ふだんは約 1 秒で終わる）
LISTENER_WAIT = 3.0
# 議事録の知らせは、相手がこの秒数だまってから言う（息つぎの間に言いかけて、続きの話で止められた。2026-10-30）
MINUTES_SETTLE = 1.2
# 話者の識別（speakers.py）は、文字から声を作る方式と Realtime API・pipeline のときだけ
SPEAKERS = VOICE == 'irodori' and (REALTIME or PIPELINE)
# Realtime API の雑音除去（make_model）
NOISE_REDUCTION = os.environ.get('CIEL_NOISE_REDUCTION', 'far_field')
# 話し終わりの判定の早さ（semantic_vad の eagerness：low・medium・high・auto）
EAGERNESS = os.environ.get('CIEL_EAGERNESS', 'medium')
# 返事の前に考える量（minimal・low・medium・high。空ならモデルの既定）
REASONING = os.environ.get('CIEL_REASONING', 'minimal')
# 返事の声ができるまでの相づち（aizuchi.py）。0 で流さない
AIZUCHI = VOICE == 'irodori' and os.environ.get('CIEL_AIZUCHI', '1') != '0'
# あいさつの前に、アプリの端末の hello（持ち主が誰か）を待つ秒数
OWNER_WAIT = float(os.environ.get('CIEL_OWNER_WAIT', '2.5'))
# 相手が長く話している途中の息つぎにも相づちを打つか（turns.py）。0 で打たない
NOD = os.environ.get('CIEL_NOD', '1') != '0'
# シエルが話している途中の短い声（咳・相づち）では止めない（interruptions.py。CIEL_INTERRUPT_SECONDS=0 で以前のやり方）
INTERRUPT_GATE = REALTIME and interruptions.CONFIRM_SECONDS > 0


def transcription(names: list[str]) -> AudioTranscription:
    """相手の発言の文字起こし（メモの元になる）。日本語と、よく出る名前のヒントを渡す。
    ヒントが無いと「シエル」が「CL」「チエル」「スチール」などになった（2026-10-16、合成音声で 3 文中 2 文。ヒントありは 3 文とも正しい）"""
    hint = '、'.join(dict.fromkeys(['シエル', *names]))[:400]
    return AudioTranscription(model='gpt-4o-mini-transcribe', language='ja',
                              prompt=f'AI キャラクター「シエル」との会話。出てくる名前：{hint}')


def make_model(names: list[str] | None = None):
    voice = os.environ.get('CIEL_OPENAI_VOICE', 'marin')
    if PIPELINE:
        return openai.LLM(model=models.model('mind'), reasoning_effort=MIND_REASONING)
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


def make_pipeline(names: list[str]) -> dict:
    """pipeline の部品（AgentSession に渡す）。音声検出は 1 つにして、文字起こしの区切りにも同じ設定を使う"""
    vad = inference.VAD()
    hint = '、'.join(dict.fromkeys(['シエル', *names]))[:400]
    model = models.model('stt')
    # gpt-realtime-whisper は名前のヒント（prompt）を受け付けない（渡すと会話が止まった。2026-10-30）。
    # gpt-live-transcribe は keywords で名前を渡せる。そのほかのモデルは prompt で渡す
    if model == 'gpt-live-transcribe':
        # 名前と、聞く係が拾う言葉（gpt-realtime-whisper では「シエル」が「シェル」、「議事録」が「二次録」になった）
        hints = {'keywords': ['シエル', '議事録', *names][:30]}
    elif model == 'gpt-realtime-whisper':
        hints = {}
    else:
        hints = {'prompt': f'AI キャラクター「シエル」との会話。出てくる名前：{hint}'}
    stt = openai.STT(model=model, language='ja', vad=vad, **hints)
    return {'vad': vad, 'stt': stt,
            # 区切り：声の調子から話し終えたかを見るモデル（手元で動く小さい版。日本語に対応）
            'turn_handling': {'turn_detection': inference.TurnDetector(version='v1-mini'),
                              # 話し終えたと決めるまでの待ち。既定（最短 0.5・最長 3 秒）では、区切りのモデルが日本語の
                              # 合成音声に自信を持てず、話し終わりから約 2.25 秒待っていた（2026-10-30、bench_compare.py）
                              'endpointing': {'mode': ENDPOINT_MODE, 'min_delay': ENDPOINT_MIN, 'max_delay': ENDPOINT_MAX},
                              # 話し終えたと決まる前から、返事の文に加えて声も作り始める
                              'preemptive_generation': {'preemptive_tts': True},
                              # シエルが話している途中の短い声（咳・相づち）では止めない（interruptions.py と同じ秒数）
                              'interruption': {'mode': 'vad', 'min_duration': interruptions.CONFIRM_SECONDS or 0.5}}}


class Ciel(Agent):
    def __init__(self) -> None:
        persona = load_persona()
        self.persona = persona
        # 道具（tools/）は、会話モデルが必要なときに呼ぶ。使い方は config/prompts/ で教える
        super().__init__(instructions=self.instructions_for('normal', 'solo'), tools=tools.TOOLS)
        self.events = emotion.ExpressionEvents()
        self.volume = volume.VoiceVolume()   # 設定画面で選んだ声の大きさ（volume.py）
        self.aizuchi = aizuchi.Backchannel(self.volume)   # 返事の声ができるまでの相づち（aizuchi.py）
        self.preamble = emotion.PreambleCut()   # 道具を呼んだ返事の前置きを止める（歌・議事録の道具が頼む）
        self.mind: mind.Mind | None = None      # pipeline の心（entrypoint がつなぐ）
        self.ear: listener.Listener | None = None   # pipeline の聞く係（entrypoint がつなぐ）
        self.style = None                        # mode.ConversationStyle（pipeline の小脳の指示を選ぶ）
        self.replies = None                      # turns.TurnReplies（pipeline で、返事の前に話者を決める）

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """pipeline：相手が話し終えた。長く話したなら相づちを流す。発言（LiveKit の会話）は書き換えない
        （書き換えると、先に作った返事が捨てられる。話者の 1 行は llm_node で、送る会話にだけ置く）"""
        if PIPELINE and self.replies is not None and not self.replies.pipeline_end_turn():
            raise StopResponse()

    def llm_node(self, chat_ctx, tools, model_settings):
        if not PIPELINE or self.mind is None:
            return Agent.default.llm_node(self, chat_ctx, tools, model_settings)
        return self._pipeline_llm(chat_ctx, tools, model_settings)

    async def _pipeline_llm(self, chat_ctx, tools, model_settings):
        """pipeline：誰が話したかを決め、心と小脳のどちらが返すかをコードで決めて（mind.py の route）、返事を流す"""
        turn = await self.replies.pipeline_turn() if self.replies is not None else {}
        if self.ear is not None:
            await self.ear.settled(LISTENER_WAIT)   # 聞く係が確かめている頼みは、受けたかが分かってから振り分ける
        who = self.mind.route(chat_ctx, turn)
        if who == 'skip':
            return   # 頼みだけの発言で、付箋になった。一言は議事録係の知らせが言う
        if who == 'mind':
            # 心：全部の指示と道具で作る（頼みごと・長い話・何人も話した・名前を呼ばれた・知らせ・道具の結果の続き）
            ctx, fns = self.mind.build(chat_ctx, turn=turn), self.mind.tools_for(chat_ctx, tools)
        else:
            # 小脳：短い指示・道具なしで、すぐ返す
            style = self.style
            brief = self.talker_instructions_for(style.talk if style else 'normal', style.presence if style else 'solo')
            ctx, fns = self.mind.build(chat_ctx, talker_instructions=brief, turn=turn), []
        # デバッグ用の会話ログ：作った文と道具の呼び出しを、最後まで作れたか（done）と一緒に残す。返事が声にも記録にも
        # ならなかったとき（止められた直後の返事）や、話す番で心が黙ったか（[silent]）を、speech・item と見比べる
        speech = getattr(self.session.current_speech, 'id', None)
        text, calls, blocked, done = [], [], [], False
        try:
            async for chunk in Agent.default.llm_node(self, ctx, fns, model_settings):
                # 渡していない道具の呼び出しは通さない（コメントから使えない道具など。mind.py の only_given）
                chunk, dropped = mind.only_given(chunk, fns)
                if dropped:
                    logger.warning('心：渡していない道具の呼び出しを止めた %s', dropped)
                    blocked += dropped
                if chunk is None:
                    continue
                delta = chunk if isinstance(chunk, str) else getattr(chunk, 'delta', None)
                if isinstance(delta, str):
                    text.append(delta)
                elif delta is not None:
                    text.append(delta.content or '')
                    calls += [c.name for c in delta.tool_calls or []]
                yield chunk
            done = True
        finally:
            debug_log.record('mind_output', who=who, speech=speech, text=''.join(text), tools=calls, done=done,
                             tools_given=len(fns), blocked=blocked)

    def talker_instructions_for(self, talk: str, presence: str) -> str:
        """小脳（pipeline のすぐの返事）の短い指示：人物像・感情の印・タッチ・すぐの返事の決まり・その場にいる人・おしゃべり度。
        話者の識別・議事録・道具の使い方は心が受け持つので入れない"""
        p = self.persona
        parts = [p.instructions + p.emotion_instructions, p.touch_instructions, p.talker_instructions, p.tasks_instructions,
                 self._presence_text(presence), self._talk_text(talk)]
        return '\n\n'.join(part.strip('\n') for part in parts if part)

    def _presence_text(self, presence: str) -> str:
        """その場にいる人（presence_*.md、覚えていることの出し方）"""
        p = self.persona
        return {'solo': p.presence_solo_instructions, 'close': p.presence_close_instructions,
                'public': p.presence_public_instructions}[presence]

    def _talk_text(self, talk: str) -> str:
        """おしゃべり度（ひかえめ talk_quiet.md・おしゃべり talk_chatty.md。ふつうは空）"""
        p = self.persona
        return {'quiet': p.talk_quiet_instructions, 'chatty': p.talk_chatty_instructions}.get(talk, '')

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
        if PIPELINE:
            parts.append(p.tasks_instructions)   # 付箋の一覧「[今のタスク]」の読み方（board.py）
        if VOICE == 'irodori':
            parts.append(p.singing_voice_instructions)   # 歌を聴く（singing.py。感想の言い方は聴き終えたときに渡す）
        if SPEAKERS:
            parts.append(self._presence_text(presence))
        if self._talk_text(talk):
            parts.append(self._talk_text(talk))
        # 1 つずつ、前の末尾の改行を落として空行 1 つでつなぐ（最後の本文の末尾はそのまま）
        instructions = parts[0]
        for part in parts[1:]:
            instructions = instructions.rstrip('\n') + '\n\n' + part
        return instructions

    def tts_node(self, text, model_settings):
        # 1 文ずつ、感情の印に合わせた声で読み上げ、Unity へ表情を送る（emotion.py）。
        # ひかえめのときに黙ると決めた返事（[silent]）は読み上げない（mode.py）
        if VOICE == 'irodori':
            speech = self.session.current_speech
            speech_id = speech.id if speech is not None else None
            return self.volume.apply(emotion.tts_node(mode.drop_silent(text), self.events, self.aizuchi,
                                                      stop=lambda spoken: self.preamble.stop(speech_id, spoken)))
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
    debug_log.start(ctx.room.name, model=MODEL, realtime_model=REALTIME_MODEL if REALTIME else None, voice=VOICE,
                    **({'mind_model': models.model('mind'), 'stt_model': models.model('stt')} if PIPELINE else {}))
    # 返事は turns.py が作らせるので、LiveKit の側でも自動で返事をしない（manual）
    # 話者の識別（speakers.py）。覚えている人は DB から読む（つなげなければ、この会話の間だけ覚える）
    store = await speaker_store.Store.open() if SPEAKERS else None
    book = speakers.SpeakerBook(store) if SPEAKERS else None
    if book is not None:
        await book.load()
    names = [k.name for k in book.known][:30] if book is not None else []   # 文字起こしのヒント（覚えている人の名前）
    session = AgentSession(llm=make_model(names), tts=irodori_tts.make() if VOICE == 'irodori' else None,
                           **(make_pipeline(names) if PIPELINE else
                              {'turn_detection': 'manual' if REALTIME else agents.NOT_GIVEN}),
                           # 読み上げる前の文字の変換は、絵文字を外すだけにする。既定の filter_markdown は、返事の頭の
                           # 感情の印「[happy]」をリンクの書きかけとみなし、返事を最後まで書き終えるまで読み上げに渡さなかった
                           # （2026-10-22、bench_latency.py。印は emotion.py が読み取って外す）
                           tts_text_transforms=['filter_emoji'],
                           userdata=tools.State(book=book))   # 道具（tools/）から使う会話の状態
    agent = Ciel()
    session.userdata.preamble = agent.preamble
    # シエルを話させる入り口は 1 つ（mouth.py）。返事・話しかけ・議事録・歌・タッチ・声の登録・あいさつが、ここを通る
    voice = session.userdata.mouth = mouth.Mouth(session)
    tap = speakers.AudioTap()
    # 返事ごとのトークン数（usage.py）。指示を短くしたときの比べる基準
    usage_log = usage.UsageLog()
    session.on('session_usage_updated', usage_log.on_usage)
    debug_log.attach(session, ctx.room, agent)

    def on_track(track: rtc.Track, publication, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO and publication.source == rtc.TrackSource.SOURCE_MICROPHONE:
            tap.attach(track)   # Unity のマイク（会議では、仮想ケーブルで届く会議の声）
    ctx.room.on('track_subscribed', on_track)

    async def send(topic: str, *messages: dict) -> None:
        # アプリへの知らせ。会話が終わって部屋が閉じたあと（議事録の清書の結果など）は送れないので、捨てる
        try:
            for msg in messages:
                await ctx.room.local_participant.publish_data(
                    json.dumps(msg, ensure_ascii=False), reliable=True, topic=topic)
        except Exception as e:
            logger.info('アプリへ送れない（%s）: %s', topic, type(e).__name__)

    def notify(msg: dict) -> None:
        # アプリへの知らせ（ciel.event）を、待たずに送る
        asyncio.create_task(send('ciel.event', msg))
    # 会話のしかた（mode.py）。いまの答え方・覚えていることの出し方は、変わるたびに Unity へ知らせる
    style = mode.ConversationStyle(agent, agent.instructions_for, can_quiet=VOICE == 'irodori')
    style.publish = notify
    history = Conversation()
    session.userdata.history = history
    # 会話のまとめ（議事録など。minutes.py）。始めと終わりは、アプリのボタン・管理用のコマンド（ciel.minutes）と、声（道具 tools/minutes.py）から
    minute_taker = minutes.Minutes(book, agent.persona.minutes_instructions, history,
                                   agent.persona.minutes_live_instructions)
    session.userdata.minutes = minute_taker
    summary_seq = 0

    def publish_summary(state) -> None:
        # まとめの中身は大きいので、分けて送る（アプリが seq ごとにつなぐ）
        nonlocal summary_seq
        summary_seq += 1
        asyncio.create_task(send('ciel.summary', *minutes.packets(state, summary_seq)))
    minute_taker.on_state = publish_summary
    minute_taker.on_progress = notify
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
    if PIPELINE:
        # 心：返事のたびに会話の記録から文脈を作る（mind.py）。話者は返事の前に turns.py が決める
        # 付箋の一覧：頼まれたこと・していることの今の状態を、心・小脳・アプリが同じ 1 つで見る（board.py）
        tasks = board.Board()
        tasks.on_change = notify
        minute_taker.board = tasks
        # 気になっていることも付箋にし、話す番が来たら心が話すかを決める（沈黙の秒数では話さない。initiative.py）
        talker.board, talker.open_nudge = tasks, agent.persona.initiative_open_nudge
        # 調べてみたいことを、自分で調べて、分かったら話の切れ目に話す（curiosity.py）
        talker.curious = curiosity.Curiosity(
            researcher, tasks, lambda text: voice.say_latest('research', settle=curiosity.SETTLE, instructions=text),
            agent.persona.research_found_nudge, style=style, paused=lambda: talker.paused is not None and talker.paused(),
            learned=talker.learn)
        agent.mind = mind.Mind(history, style=style, minutes=minute_taker, initiative=talker,
                               quiet_turn=agent.persona.talk_quiet_turn_instructions,
                               brief_instructions=agent.persona.mind_brief_instructions, board=tasks)
        voice.before_say = agent.mind.on_say   # 議事録・歌の知らせ・声の登録の一言は心が作る
        agent.mind.waiting = voice.waiting     # 切れ目を待っている知らせは、相手への返事の中で伝える

        def on_said(ev) -> None:
            # 知らせを添えた返事を言い終えたら、その知らせはあとで言わない（途中で止められたら、知らせは待ち続ける）
            item = ev.item
            if getattr(item, 'role', None) != 'assistant' or agent.mind.handed is None:
                return
            if not getattr(item, 'interrupted', False) and (item.text_content or '').strip():
                voice.drop(agent.mind.handed)
            agent.mind.handed = None
        session.on('conversation_item_added', on_said)
        # 聞く係：話の途中の議事録の頼みを、文字起こしの区切りごとに見つけて、コードが直接動かす（listener.py）
        agent.ear = listener.Listener(history, minute_taker, agent.persona.listener_instructions, board=tasks)
        session.on('user_input_transcribed', agent.ear.on_transcribed)
        agent.replies, agent.style = replies, style
        replies.stall_watch = False   # 区切りは LiveKit が決めるので、Realtime の区切りが来ない見張りは使わない
    session.userdata.initiative = talker   # 道具 read_inner_thoughts・keep_thought が、心の中を読む・預ける
    # 歌を聴く（singing.py）。聴いているあいだは会話モデルへ声を送らず、シエルから話しかけない
    song = singing.SongListener(session, tap, agent.persona.singing_feedback) if VOICE == 'irodori' else None
    session.userdata.song = song
    if song is not None:
        song.publish = notify
        talker.paused = lambda: song.active
        song.on_end = talker.interlude   # 歌の前の考えを、歌のあとで話さない
        song.preamble = agent.preamble   # 「どうぞ」を 2 文までにする
    session.on('user_state_changed', talker.on_user_state)
    session.on('agent_state_changed', talker.on_agent_state)
    if REALTIME:
        session.on('user_state_changed', replies.on_user_state)
        session.on('user_input_transcribed', replies.on_transcribed)   # 文字起こしの確定で返事を作らせる
        session.on('conversation_item_added', replies.on_item)   # 多人数で、シエルの質問への答えを待つ
    elif PIPELINE:
        session.on('user_state_changed', replies.on_user_state)   # 話者の区間・話している途中の相づち
    if SPEAKERS:
        asyncio.create_task(replies.load_encoder())

    # その人について覚えておくメモを、会話の裏で書く（notes.py。覚えている人で、お話を覚えることに同意した人だけ）
    note_taker = notes.NoteTaker(book, agent.persona.notes_instructions, history) if book is not None and store else None
    session.userdata.notes = note_taker   # 道具 remember_about_speaker が、覚えることを記録係に預ける
    # シエルがその人をどう思っているか（relationship.py）。会話の終わりに、この会話を振り返って書き直す
    relation_keeper = (relationship.RelationKeeper(book, note_taker, agent.persona.relationship_instructions, history)
                       if note_taker is not None else None)

    def on_minutes(what: str) -> None:
        # シエルに一言告げさせ（config/prompts/minutes_voice.md）、アプリのボタンの表示を合わせる。
        # 話の途中で頼まれたとき（聞く係）もあるので、話の切れ目まで待ってから、そのとき最新の知らせだけを言う
        voice.say_latest('minutes', settle=MINUTES_SETTLE,
                         instructions=minutes.LINES[what] + '\n\n' + minute_taker.context())
        notify({'v': 1, 'type': 'minutes.state', 'recording': minute_taker.recording})
    minute_taker.on_change = on_minutes
    # 声で送り先を切り替えたら、アプリの端末に覚えさせる（次につないだときも同じ送り先にする）
    minute_taker.on_destination = lambda name: notify({'v': 1, 'type': 'minutes.destination', 'selected': name})
    minute_taker.busy = voice.busy   # 送り終えたことは、話の切れ目で伝える
    if note_taker is not None:
        book.on_notes_consent = note_taker.on_consent   # 同意したら、同意の前に話したことも含めてすぐ書く
    if book is not None:
        book.on_split = history.on_split
        book.on_merge = history.on_merge
        # アプリの参加者パネル（speakers.py の state）。名簿・最後に話した人が変わるたびに知らせる
        book.on_change = notify
        # ひとり・身近な人のときは、端末の持ち主の声を優先して当てる（speakers.py の _owner_judge）
        book.private = lambda: style.presence in ('solo', 'close')
        # 声の登録（アプリの「声を登録する」）：様子をアプリへ知らせ、その間はシエルから話しかけない。登録できたらひとこと言う
        book.on_enroll = notify
        async def enrolled(name: str) -> None:
            # 最後の文を読み終えるまで待ってから言う（読んでいる途中に話し始めて、止められたことがあった）
            await asyncio.sleep(1.0)
            await voice.say_when_free('enrolled', wait=10.0, anyway=True, tool_choice='none',
                                      instructions=agent.persona.enroll_done.replace('{name}', name))
        book.on_enrolled = lambda name: asyncio.create_task(enrolled(name))
        talker.paused = lambda: book.enrolling is not None or (song is not None and song.active)
    # 書き起こし・発言時刻・その区間の話者を共通履歴へ一度だけ記録する。
    recorder = ConversationRecorder(history, replies, note_taker)
    session.on('user_input_transcribed', recorder.on_transcribed)
    session.on('conversation_item_added', recorder.on_item)

    async def close_store() -> None:
        usage_log.summary()
        voice.summary()
        debug_log.record('end')
        await recorder.flush()   # 話者を決めている途中の発言も渡してから
        await researcher.close()
        if song is not None:
            await song.close()   # 聴いている途中の歌声は捨てる
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
    # アプリは、会話サーバーが部屋に入るとすぐ、会話のしかたと端末の持ち主の hello を送る。受け損ねないように、入る前に受け口を作る
    ctx.room.on('data_received', style.on_data)
    if book is not None:
        ctx.room.on('data_received', book.on_data)
    # 会話の録音・文字起こしを LiveKit Cloud に残さない（仕様書 8 章：ユーザーの音声と会話を保存しない）
    await session.start(room=ctx.room, agent=agent, record=False)
    # アプリの「まとめをとる」で選べるテンプレート（minutes.py）
    await send('ciel.event', minute_taker.templates_event())
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
    # 議事録の始めと終わり（minutes.py。アプリのボタンと minutes_admin.py が送る）
    ctx.room.on('data_received', minute_taker.on_data)
    # 歌を聴く（singing.py。アプリの札が「歌い終わった」を送る）
    if song is not None:
        ctx.room.on('data_received', song.on_data)
    # 参加者パネル（speakers.py。受け口は session.start の前に作った）
    if book is not None:
        book.notify()
    # シエルの声の大きさ（volume.py。アプリの設定画面が知らせる）
    ctx.room.on('data_received', agent.volume.on_data)
    # アプリが部屋に入った直後に送った知らせは、会話サーバーの受け取りの準備ができる前で、届かないことがある
    # （2026-10-24、開発用の試験で 3 回に 2 回、hello か会話のしかたが届かなかった）。準備ができたので、もう一度送ってもらう
    await send('ciel.event', {'v': 1, 'type': 'device.hello_request'})
    # あいさつでは道具を使わせない（まだ誰も話していないのに、話者の状態を調べて「声の登録がまだ」と話したことがあった）
    # 今の日付・時間帯（clock.py）も添える（「おはよう」「こんばんは」を合わせる）
    await voice.say('greeting', instructions=clock.now_line() + '\n\n' + await greeting(agent, book, style),
                                 tool_choice='none')
    talker.start()
    if agent.mind is not None:
        agent.mind.start()   # 心が「今のまとめ」を書く見回り
    if AIZUCHI:
        await agent.aizuchi.prepare(ctx.room)   # あいさつのあとに、相づちの声を読み上げておく


async def greeting(agent, book, style) -> str:
    """会話の始めのあいさつの指示。アプリの hello で端末の持ち主が分かれば（ひとり・身近な人のとき）、名前を呼んであいさつする。
    hello は会話サーバーが部屋に入ってからアプリが送るので、少しだけ待つ（古いアプリは送らないので、待ちすぎない）"""
    if book is None:
        return agent.persona.greeting
    try:
        await asyncio.wait_for(book.device_known.wait(), OWNER_WAIT)
    except asyncio.TimeoutError:
        logger.info('端末の hello が %.1f 秒で届かなかった（ふつうのあいさつ）', OWNER_WAIT)
        return agent.persona.greeting
    about = await book.greeting_context(style.presence in ('solo', 'close'))
    if not about:
        return agent.persona.greeting
    return agent.persona.greeting_owner.replace('{name}', book.owner_name) + '\n\n' + about


if __name__ == '__main__':
    agents.cli.run_app(server)
