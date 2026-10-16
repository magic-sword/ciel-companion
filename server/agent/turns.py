# -*- coding: utf-8 -*-
"""発言が終わったら、返事を作らせる（会話モデルの自動の返事は止めてある。agent.py の make_model）。

- 返事を作らせるのは、会話モデルの側（Realtime API の semantic_vad）が発言を区切り、その文字起こしが確定したとき。
  そのときには、その発言の声が会話に入っているので、「[発言者：…]」の 1 行がその声の後ろに入り、返事がその発言に答える。
  話し始め・話し終わり（user_state）だけを見て作らせると、LiveKit の手元の VAD（silero）が読点の 0.5 秒の間でも
  区切るので、発言の声が会話に入る前に返事を作らせてしまい、1 つ前の発言に答えていた（2026-10-16、合成した声の試験）。
- 文字起こしが確定したときに、もう次を話し始めていたら（「シエル、……」の読点で区切られたとき）、まだ作らせず、
  続きの文字起こしの確定を待って、まとめて 1 回だけ作らせる。短い発言は、続きを話し始めないか少し待ってから作らせる。
  文字起こしが空（物音など）なら作らせない。
- その発言の声で話者を判定し（speakers.py）、「[発言者：…]」を足してから返事を作らせる（2 人でも多人数でも）。
  2 人のときは、知らない声なら名前を聞く（config/prompts/speakers.md）。声は、まとめた発言の最初の話し始めから
  最後の話し終わりまでを使う。
- 多人数のときは、次のどちらかのときだけ返事を作らせる。それ以外は作らせない（声は会話に残るので、話の流れは覚えている）。
  - 文字起こしに「シエル」（や「AI」）がある。
  - シエルが直前に質問で終わる返事をして、まだ FOLLOW_SECONDS たっていない（その答えかもしれない）。
  作らせるときも、答えるか黙るか（[silent]）は会話モデルが決める。返事ごとに group_turn.md の短い念押しを添える
  （generate_reply の instructions は、会話の指示の後ろに足される）。会話の指示の group.md だけでは、呼ばれていない
  発言にも答えることが多く、一度答えると、続く人どうしの話も自分への返事と受け取って答え続けた（2026-10-16）。
- 話者の識別が使えないとき（ECAPA の読み込み前・失敗、CIEL_VOICE が irodori 以外）は、[発言者] なしで作らせる。
"""
import asyncio
import logging
import re
import time

from livekit.agents import AgentSession
from livekit.agents.voice.events import UserInputTranscribedEvent, UserStateChangedEvent

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
# 多人数のとき、これが文字起こしにあれば、シエルが呼ばれたかもしれないとして返事を作らせる
CALL_WORDS = ('シエル', 'しえる', 'AI', 'ＡＩ', 'エーアイ')
# 多人数のとき、シエルが質問で終わる返事をしてから、その答えを待つ時間
FOLLOW_SECONDS = 20.0
TAGS = re.compile(r'\[[a-z]+\]')


class TurnReplies:
    def __init__(self, session: AgentSession, book: speakers.SpeakerBook, tap: speakers.AudioTap, switch,
                 group_turn: str) -> None:
        self.session = session
        self.book = book
        self.tap = tap
        self.switch = switch          # mode.ModeSwitch（2 人か多人数か）
        self.group_turn = group_turn  # 多人数のとき、返事ごとに添える念押し（config/prompts/group_turn.md）
        self.encoder: speakers.Encoder | None = None
        self._speaking = False
        self._started_at: float | None = None   # まだ返事を作らせていない発言の、最初の話し始め
        self._ended_at: float | None = None     # その最後の話し終わり
        self._pending = False                   # 文字起こしは確定したが、次を話していたので待たせている
        self._texts: list[str] = []             # その文字起こし（多人数のとき、呼ばれたかを見る）
        self._asked_at: float | None = None     # シエルが質問で終わる返事をした時刻
        self._later: asyncio.TimerHandle | None = None   # 待たせている返事を作らせる時計
        self._no_text: asyncio.TimerHandle | None = None
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
            if self._started_at is None:
                self._started_at = ev.created_at
        elif ev.new_state == 'listening' and ev.old_state == 'speaking':
            self._speaking = False
            self._ended_at = ev.created_at
            if self._pending:
                self._reply_later(STALE_SECONDS)

    def on_transcribed(self, ev: UserInputTranscribedEvent) -> None:
        if not ev.is_final:
            if not ev.transcript and self._no_text is None:
                # 会話モデルの側が発言を区切った（LiveKit が空の途中経過で知らせる）。文字起こしの確定を待つ
                self._cancel_later()
                self._no_text = asyncio.get_running_loop().call_later(NO_TEXT_SECONDS, self._text_failed)
            return
        self._cancel_no_text()
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
        """シエルの返事が会話に入ったら、質問で終わったかを覚えておく（多人数で、その答えを待つため）"""
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
        if self.switch.mode == 'group' and not self._called(text):
            log.info('多人数の会話：呼ばれていないので、返事を作らせない')
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

    async def _reply(self, start: float, end: float) -> None:
        extra = {'instructions': self.group_turn} if self.switch.mode == 'group' else {}
        if self.book is None or self.encoder is None:
            self.session.generate_reply(**extra)
            return
        t0 = time.perf_counter()
        audio = speakers.voiced(self.tap.window(start - speakers.LEAD_SECONDS, end))
        seconds = len(audio) / speakers.SR
        e = None
        if seconds >= speakers.MIN_VOICED:
            e = await asyncio.get_running_loop().run_in_executor(None, self.encoder.embed, audio)
        line = await self.book.identify(e, seconds, solo=self.switch.mode != 'group')
        log.info('話者の判定 %.0f ms（声 %.1f 秒）', (time.perf_counter() - t0) * 1000, seconds)
        if line is not None:
            extra['user_input'] = line
        self.session.generate_reply(**extra)
