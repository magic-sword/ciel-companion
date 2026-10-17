# -*- coding: utf-8 -*-
"""発言が終わったら、返事を作らせる（会話モデルの自動の返事は止めてある。agent.py の make_model）。

- 返事を作らせるのは、会話モデルの側（Realtime API の semantic_vad）が発言を区切ったとき（speech_stopped。
  そのときには、その発言の声が会話に入っているので、「[発言者：…]」の 1 行がその声の後ろに入り、返事がその発言に答える）。
  - ふつう・おしゃべりのとき：文字起こしの確定を待たない。区切りから SETTLE_SECONDS（短い発言は SHORT_SETTLE_SECONDS）
    だけ、続きを話し始めないかを見てから作らせる。その間に声の特徴を計算しておく。文字起こしを待つと 0.35 秒、
    短い発言はさらに 0.6 秒遅れていた（2026-10-17、bench_latency.py）。大きな声がほとんど無い発言（物音かもしれない）だけは、
    文字起こしを待ち、文字になったら作らせる。区切ったあとで続きを話し始めたら、作らせた返事は会話モデルの側が取り消し、
    続きの区切りでもう一度作らせる。
  - ひかえめのとき：呼ばれたかを文字起こしで見るので、文字起こしの確定を待つ（以下）。
  話し始め・話し終わり（user_state）だけを見て作らせると、LiveKit の手元の VAD（silero）が読点の 0.5 秒の間でも
  区切るので、発言の声が会話に入る前に返事を作らせてしまい、1 つ前の発言に答えていた（2026-10-16、合成した声の試験）。
- 文字起こしが確定したときに、もう次を話し始めていたら（「シエル、……」の読点で区切られたとき）、まだ作らせず、
  続きの文字起こしの確定を待って、まとめて 1 回だけ作らせる。短い発言は、続きを話し始めないか少し待ってから作らせる。
  文字起こしが空（物音など）なら作らせない。
- その発言の声で話者を判定し（speakers.py）、「[発言者：…]」を足してから返事を作らせる（どの設定でも）。
  知らない声なら名前を聞く（config/prompts/speakers.md）。声は、まとめた発言の最初の話し始めから
  最後の話し終わりまでを使う。判定するたびに、この会話で聞いた声の数を mode.py へ知らせる（その場にいる人の自動）。
  本人のメモを渡すかは、その場にいる人で決める（ひとり・身近な人なら渡す）。
- おしゃべり度が「ひかえめ」のとき（mode.py）は、次のどちらかのときだけ返事を作らせる。それ以外は作らせない
  （声は会話に残るので、話の流れは覚えている）。
  - 文字起こしに「シエル」（や「AI」）がある。
  - シエルが直前に質問で終わる返事をして、まだ FOLLOW_SECONDS たっていない（その答えかもしれない）。
  作らせるときも、答えるか黙るか（[silent]）は会話モデルが決める。返事ごとに talk_quiet_turn.md の短い念押しを添える
  （generate_reply の instructions は、会話の指示の後ろに足される）。会話の指示の talk_quiet.md だけでは、呼ばれていない
  発言にも答えることが多く、一度答えると、続く人どうしの話も自分への返事と受け取って答え続けた（2026-10-16）。
- 話者の識別が使えないとき（ECAPA の読み込み前・失敗、CIEL_VOICE が irodori 以外）は、[発言者] なしで作らせる。
- 相づち（aizuchi.py）：返事を頼むときに 1 つ流す。相手が長く話している途中（会話モデルの側はまだ区切っていない）の
  息つぎにも打つ（_watch_pauses）。話し始めて（前の相づちから）NOD_AFTER_SECONDS たち、直前の話し声より NOD_QUIET_DB
  小さい音が NOD_PAUSE_SECONDS 続いたら。相づちのすぐあと（NOD_SKIP_SECONDS 以内）に話し終えたら、返事の前の相づちは流さない。
  ひかえめのとき・シエルが話しているときは打たない。
- 話しながらシエルに触れたとき（touch.py が知らせを持っている）は、その発言の [発言者：…] の後ろにタッチの 1 行を添える
  （その声の人が触ったと分かる）。ひかえめで呼ばれていなくても、触れられたら返事を作らせる。
"""
import asyncio
import logging
import re
import time

import numpy as np
from livekit.agents import AgentSession
from livekit.agents.voice.events import UserInputTranscribedEvent, UserStateChangedEvent

import latency
import speakers

log = logging.getLogger('ciel-agent.turns')

# 手元の VAD だけが話し始めたと言い、会話モデルの側が発言にしなかったとき（物音など）に、
# 待たせている返事を作らせるまでの時間（話し終わりから）
STALE_SECONDS = 2.0
# 短い発言（「シエル、」「えっと、」）は続きがあることが多いので、文字起こしの確定から少し待ってから作らせる
SHORT_SECONDS = 1.2
GRACE_SECONDS = 0.6
# 会話モデルの側が発言を区切ったのに、文字起こしが確定しない（失敗した）ときに、それでも作らせるまでの時間
NO_TEXT_SECONDS = 5.0
# ひかえめのとき、これが文字起こしにあれば、シエルが呼ばれたかもしれないとして返事を作らせる
CALL_WORDS = ('シエル', 'しえる', 'AI', 'ＡＩ', 'エーアイ')
# ひかえめのとき、シエルが質問で終わる返事をしてから、その答えを待つ時間
FOLLOW_SECONDS = 20.0
TAGS = re.compile(r'\[[a-z]+\]')
# ふつう・おしゃべりのとき、区切りのあと、続きを話し始めないかを見る時間（会話モデルの側は、読点の間で区切ったあと
# 0.05〜0.3 秒で次の話し始めを知らせた）。短い発言（「シエル、」）は続きがあることが多いので長めに見る
SETTLE_SECONDS = 0.25
SHORT_SETTLE_SECONDS = 0.35
# 話している途中の相づち（_watch_pauses）
NOD_AFTER_SECONDS = 3.0    # 話し始めて（前の相づちから）これだけたってから
NOD_PAUSE_SECONDS = 0.4    # 息つぎ（小さな音）がこれだけ続いたら
NOD_QUIET_DB = 20.0        # 直前 3 秒の話し声（大きいほうから 1 割の大きさ）より、これだけ小さければ息つぎ
NOD_SKIP_SECONDS = 2.0     # 相づちからこれ以内に話し終えたら、返事の前の相づちは流さない
# 大きな声（LOUD_DB 以上の 20 ms）がこれより短い発言は、物音かもしれないので文字起こしを待つ
LOUD_DB = -40.0
LOUD_SECONDS = 0.2


class TurnReplies:
    def __init__(self, session: AgentSession, book: speakers.SpeakerBook, tap: speakers.AudioTap, style,
                 quiet_turn: str, backchannel=None) -> None:
        self.session = session
        self.book = book
        self.tap = tap
        self.style = style            # mode.ConversationStyle（おしゃべり度・その場にいる人）
        self.quiet_turn = quiet_turn  # ひかえめのとき、返事ごとに添える念押し（config/prompts/talk_quiet_turn.md）
        self.backchannel = backchannel   # 返事の頭の相づち（aizuchi.Backchannel。irodori のときだけ）
        self.encoder: speakers.Encoder | None = None
        self.touch = None             # touch.TouchReactions（話しながら触れたときの知らせ。agent.py がつなぐ）
        self._speaking = False
        self._started_at: float | None = None   # まだ返事を作らせていない発言の、最初の話し始め
        self._ended_at: float | None = None     # その最後の話し終わり
        self._pending = False                   # 文字起こしは確定したが、次を話していたので待たせている
        self._texts: list[str] = []             # その文字起こし（多人数のとき、呼ばれたかを見る）
        self._asked_at: float | None = None     # シエルが質問で終わる返事をした時刻
        self._later: asyncio.TimerHandle | None = None   # 待たせている返事を作らせる時計
        self._no_text: asyncio.TimerHandle | None = None
        self._early: asyncio.Task | None = None   # 区切りのあと、続きを見てから作らせる（ふつう・おしゃべり）
        self._await_text = False                  # 物音かもしれないので、文字起こしを待っている
        self.nod = True                           # 話している途中の相づちを打つか（agent.py の CIEL_NOD）
        self._watch: asyncio.Task | None = None   # 話している途中の息つぎを見る
        self._nod_at = 0.0                        # 最後に話の途中の相づちを打った時刻
        self._tasks: set[asyncio.Task] = set()

    async def load_encoder(self) -> None:
        """声の特徴の計算の準備（数秒かかるので、会話の始めに裏で読み込む）"""
        try:
            self.encoder = await asyncio.get_running_loop().run_in_executor(None, speakers.Encoder.get)
        except Exception:
            log.exception('ECAPA を読み込めない（話者は「不明」になる）')

    def on_user_state(self, ev: UserStateChangedEvent) -> None:
        if ev.new_state == 'speaking':
            self._speaking = True
            self._cancel_later()
            self._cancel_early()   # 続きを話し始めた。続きの区切りで、まとめて作らせる
            if self.backchannel is not None:
                self.backchannel.stop()
            if self._started_at is None:
                self._started_at = ev.created_at
            if self.backchannel is not None and self.nod and (self._watch is None or self._watch.done()):
                self._watch = asyncio.create_task(self._watch_pauses())
        elif ev.new_state == 'listening' and ev.old_state == 'speaking':
            self._speaking = False
            self._ended_at = ev.created_at
            if self._pending:
                self._reply_later(STALE_SECONDS)

    def on_transcribed(self, ev: UserInputTranscribedEvent) -> None:
        if not ev.is_final:
            if not ev.transcript:
                # 会話モデルの側が発言を区切った（LiveKit が空の途中経過で知らせる）
                latency.start()
                self._cancel_later()
                if self.backchannel is not None:
                    self.backchannel.new_turn()
                if self.style.talk != 'quiet':
                    self._settle()
                elif self._no_text is None:   # ひかえめ：文字起こしの確定を待つ
                    self._no_text = asyncio.get_running_loop().call_later(NO_TEXT_SECONDS, self._text_failed)
            return
        self._cancel_no_text()
        latency.mark('文字起こし')
        if self.backchannel is not None and ev.transcript.strip():
            self.backchannel.heard(ev.transcript)   # 質問なら、考えるときの相づちにする
        if self.style.talk != 'quiet':
            # ふつう・おしゃべり：返事は区切りで作らせている。物音かもしれず待っていた発言だけ、文字になったら作らせる
            if self._await_text:
                self._await_text = False
                if ev.transcript.strip():
                    self._reply_now()
                else:
                    self._forget()
            return
        if not ev.transcript.strip():
            if not self._pending:
                self._forget()   # 文字にならない音だった。返事は作らせない
            return
        self._texts.append(ev.transcript)
        if self._speaking:
            self._pending = True   # 読点の間などで区切られた。続きと合わせて 1 回にする
            log.info('発言の続きを待つ')
            return
        if self._started_at is not None and (self._ended_at or time.time()) - self._started_at < SHORT_SECONDS:
            self._pending = True   # 短い発言。すぐに続きを話し始めたら、合わせて 1 回にする
            self._reply_later(GRACE_SECONDS)
            return
        self._reply_now()

    async def _watch_pauses(self) -> None:
        """話している途中の息つぎを見つけて、相づちを打つ（会話モデルの側が区切るまで）"""
        n = speakers.SR // 50
        while self._speaking:
            await asyncio.sleep(0.05)
            now = time.time()
            if (self.style.talk == 'quiet' or self.session.agent_state == 'speaking' or self._started_at is None
                    or now - max(self._started_at, self._nod_at) < NOD_AFTER_SECONDS):
                continue
            raw = self.tap.window(now - 3.0, now)
            frames = raw[: len(raw) // n * n].reshape(-1, n)
            pause = int(NOD_PAUSE_SECONDS * 50)
            if len(frames) < pause + 25:
                continue
            db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
            talk = float(np.percentile(db[:-pause], 90))
            # 息つぎの前の 0.5 秒に話し声があり、そのあと小さな音が続いている
            if talk > -45 and db[-pause - 25:-pause].max() > talk - 6 and db[-pause:].max() < talk - NOD_QUIET_DB:
                if self.backchannel.nod():
                    self._nod_at = now

    def _settle(self) -> None:
        """ふつう・おしゃべり：区切りのあと、続きを話し始めないかを少し見てから作らせる"""
        now = time.time()
        start, end = self._started_at or now, self._ended_at or now
        raw = self.tap.window(start - speakers.LEAD_SECONDS, end)
        n = speakers.SR // 50
        frames = raw[: len(raw) // n * n].reshape(-1, n)
        loud = float((20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9) > LOUD_DB).sum()) * 0.02 if len(frames) else 0.0
        if loud < LOUD_SECONDS:
            log.info('大きな声が %.2f 秒だけ。文字起こしを待つ', loud)
            self._await_text = True
            return
        self._await_text = False
        self._cancel_early()
        settle = SHORT_SETTLE_SECONDS if end - start < SHORT_SECONDS else SETTLE_SECONDS
        self._early = t = asyncio.create_task(self._settle_then_reply(start, end, settle))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _settle_then_reply(self, start: float, end: float, settle: float) -> None:
        voice = self._embed(start, end)   # 待つあいだに、声の特徴を計算しておく
        await asyncio.sleep(settle)
        if self._speaking:
            return
        self._early = None
        self._forget()
        await self._reply(start, end, voice)

    def _cancel_early(self) -> None:
        if self._early is not None:
            self._early.cancel()
            self._early = None

    def _reply_later(self, seconds: float) -> None:
        self._cancel_later()
        self._later = asyncio.get_running_loop().call_later(seconds, self._reply_now)

    def _text_failed(self) -> None:
        self._no_text = None
        log.warning('文字起こしが確定しないので、そのまま返事を作らせる')
        if not self._speaking:
            self._reply_now()

    def _cancel_no_text(self) -> None:
        if self._no_text is not None:
            self._no_text.cancel()
            self._no_text = None

    def on_item(self, ev) -> None:
        """シエルの返事が会話に入ったら、質問で終わったかを覚えておく（ひかえめのとき、その答えを待つため）"""
        if getattr(ev.item, 'role', None) != 'assistant':
            return
        text = TAGS.sub('', ev.item.text_content or '').strip()
        self._asked_at = time.time() if text.endswith(('？', '?')) else None

    def _called(self, text: str) -> bool:
        if any(w in text.upper() for w in CALL_WORDS):
            return True
        return self._asked_at is not None and time.time() - self._asked_at < FOLLOW_SECONDS

    def _reply_now(self) -> None:
        self._cancel_later()
        start, end, text = self._started_at, self._ended_at, ''.join(self._texts)
        self._forget()
        touched = self.touch is not None and self.touch.pending is not None
        if self.style.talk == 'quiet' and not self._called(text) and not touched:
            log.info('ひかえめ：呼ばれていないので、返事を作らせない')
            return
        now = time.time()
        t = asyncio.create_task(self._reply(start or now, end or now))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def _forget(self) -> None:
        self._started_at = self._ended_at = None
        self._pending = False
        self._texts = []

    def _cancel_later(self) -> None:
        if self._later is not None:
            self._later.cancel()
            self._later = None

    def _embed(self, start: float, end: float) -> tuple[float, asyncio.Future | None]:
        """その発言の声の長さと、声の特徴の計算（裏で始める。短すぎる・ECAPA が無いときは None）"""
        if self.book is None or self.encoder is None:
            return 0.0, None
        audio = speakers.voiced(self.tap.window(start - speakers.LEAD_SECONDS, end))
        seconds = len(audio) / speakers.SR
        if seconds < speakers.MIN_VOICED:
            return seconds, None
        return seconds, asyncio.get_running_loop().run_in_executor(None, self.encoder.embed, audio)

    async def _reply(self, start: float, end: float, voice: tuple[float, asyncio.Future | None] | None = None) -> None:
        extra = {'instructions': self.quiet_turn} if self.style.talk == 'quiet' else {}
        # 相づち（aizuchi.py）：ひかえめ（黙ると決めることがある）と短い発言には流さない
        if (self.backchannel is not None and self.style.talk != 'quiet' and end - start >= SHORT_SECONDS
                and not self.backchannel.played_within(NOD_SKIP_SECONDS)):
            latency.mark('相づち')
            self.backchannel.play()
        if self.book is None or self.encoder is None:
            touch = self.touch.take() if self.touch is not None else None
            if touch is not None:
                extra['user_input'] = touch
            latency.mark('返事を頼んだ')
            self.session.generate_reply(**extra)
            return
        t0 = time.perf_counter()
        seconds, pending = voice if voice is not None else self._embed(start, end)
        e = await pending if pending is not None else None
        presence = self.style.presence
        line = await self.book.identify(e, seconds, solo=presence == 'solo', push_notes=presence in ('solo', 'close'))
        self.style.on_voices(len(self.book.speakers))
        if self.book.last is not None:
            self.book.last_at = time.monotonic()   # 最後に話した人を、触った人とみなせる時間（touch.py）
        log.info('話者の判定 %.0f ms（声 %.1f 秒）', (time.perf_counter() - t0) * 1000, seconds)
        touch = self.touch.take() if self.touch is not None else None
        if touch is not None:
            line = (line + '\n' + touch) if line is not None else touch
        if line is not None:
            extra['user_input'] = line
        latency.mark('返事を頼んだ')
        self.session.generate_reply(**extra)
