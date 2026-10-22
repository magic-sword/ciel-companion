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
- 会話モデルの側が区切った発言（区間）ごとに、話し終わったらすぐ、その声で誰が話したかを 1 回だけ決める（_judge）。
  返事を作らせるときの「[発言者：…]」も、文字起こしの話者（メモの記録係・議事録の係。speaker_of）も、この判定を使う
  （別々に計算すると、同じ発言でも食い違うことがあった）。返事を作るかどうかに関係なく、発言ごとに必ず決める。「最後に判定した人」を使うと、
  ひかえめで返事をしない発言・小さな声・判定より先に届いた文字起こしが、前の人の発言になってしまったため（2026-10-18）。
  書き起こしの会話項目が持つ発言開始時刻で区間と組にする。時刻を取得できない場合だけ古い順に組にする。
"""
import asyncio
import collections
import logging
import os
import re
import time
from dataclasses import dataclass

import numpy as np
from livekit.agents import AgentSession
from livekit.agents.voice.events import UserInputTranscribedEvent, UserStateChangedEvent

import debug_log
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
# 0.05〜0.3 秒で次の話し始めを知らせた）。短い発言（「シエル、」）は続きがあることが多いので長めに見る。
# 試すときは環境変数で変える（CIEL_SETTLE_SECONDS・CIEL_SHORT_SETTLE_SECONDS）
SETTLE_SECONDS = float(os.environ.get('CIEL_SETTLE_SECONDS', '0.25'))
SHORT_SETTLE_SECONDS = float(os.environ.get('CIEL_SHORT_SETTLE_SECONDS', '0.35'))
# 話している途中の相づち（_watch_pauses）
NOD_AFTER_SECONDS = 3.0    # 話し始めて（前の相づちから）これだけたってから
NOD_PAUSE_SECONDS = 0.4    # 息つぎ（小さな音）がこれだけ続いたら
NOD_QUIET_DB = 20.0        # 直前 3 秒の話し声（大きいほうから 1 割の大きさ）より、これだけ小さければ息つぎ
NOD_SKIP_SECONDS = 2.0     # 相づちからこれ以内に話し終えたら、返事の前の相づちは流さない
# 大きな声（LOUD_DB 以上の 20 ms）がこれより短い発言は、物音かもしれないので文字起こしを待つ
LOUD_DB = -40.0
LOUD_SECONDS = 0.2
# 発言の区間を、文字起こしと組にするまで取っておく時間（これより古い区間は、文字起こしが来なかったものとして捨てる）
SEGMENT_KEEP_SECONDS = 20.0
# 返事ごとに変わる情報の渡し方（2026-10-22）。
#   instructions … 話者の行・議事録の状態を、返事ごとの指示に足す（以前のやり方）。LiveKit は返事ごとの指示を
#                  「会話の指示＋足した分」に置き換えて送るので、足した分が前と変わると、指示から後ろ（道具の説明・会話の履歴）の
#                  キャッシュが効かなくなる
#   items        … 話者の行は相手の発言のすぐ後ろ、議事録の状態は変わったときだけ、会話の後ろに system の項目として置く。
#                  会話の指示が毎回同じになり、過去の発言にも誰が話したかが残る。覚えている人のメモ・関係は、人前になったら
#                  すぐ外せるように、今までどおり返事ごとの指示に足す
TURN_CONTEXT = os.environ.get('CIEL_TURN_CONTEXT', 'instructions')


@dataclass
class Segment:
    """会話モデルの側が区切った発言 1 つ（話し始め〜話し終わり）と、その声での話者の判定（裏で決める）"""
    start: float
    end: float
    judgment: 'asyncio.Task | None'   # speakers.Judgment を返す。ECAPA が無いときは None
    turn: object | None = None  # conversation.Turn。文字起こしより先に発言順を確保する


class TurnReplies:
    def __init__(self, session: AgentSession, book: speakers.SpeakerBook, tap: speakers.AudioTap, style,
                 quiet_turn: str, backchannel=None, *, history=None, minutes=None, nod: bool = True) -> None:
        self.session = session
        self.book = book
        self.tap = tap
        self.style = style            # mode.ConversationStyle（おしゃべり度・その場にいる人）
        self.quiet_turn = quiet_turn  # ひかえめのとき、返事ごとに添える念押し（config/prompts/talk_quiet_turn.md）
        self.backchannel = backchannel   # 返事の頭の相づち（aizuchi.Backchannel。irodori のときだけ）
        self.history = history        # 接続中の共通履歴（conversation.Conversation）
        self.minutes = minutes        # minutes.Minutes。返答のたびに実際の記録状態を渡す
        self.nod = nod                # 話している途中の相づちを打つか（agent.py の CIEL_NOD）
        self._minutes_context: str | None = None   # 会話の後ろに最後に置いた議事録の状態（TURN_CONTEXT=items）
        self._thinking = False   # アプリに「考えています」と知らせている（_set_thinking）
        self.encoder: speakers.Encoder | None = None
        # touch.TouchReactions（話しながら触れたときの知らせ）。会話が始まってから作るので、agent.py があとでつなぐ
        self.touch = None
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
        self._watch: asyncio.Task | None = None   # 話している途中の息つぎを見る
        self._nod_at = 0.0                        # 最後に話の途中の相づちを打った時刻
        self._tasks: set[asyncio.Task] = set()
        self._segment_start: float | None = None             # いま話している発言の話し始め（区間ごと。返事とは別）
        self._segments: list[Segment] = []                  # 文字起こしをまだ組にしていない発言の区間
        self._recent: collections.deque[Segment] = collections.deque(maxlen=20)   # 最近の発言の区間（返事のため）

    async def load_encoder(self) -> None:
        """声の特徴の計算の準備（数秒かかるので、会話の始めに裏で読み込む）"""
        try:
            self.encoder = await asyncio.get_running_loop().run_in_executor(None, speakers.Encoder.get)
        except Exception:
            log.exception('ECAPA を読み込めない（話者は「不明」になる）')

    def on_user_state(self, ev: UserStateChangedEvent) -> None:
        if ev.new_state == 'speaking':
            self._segment_start = ev.created_at
            self._speaking = True
            self._cancel_later()
            self._cancel_early()   # 続きを話し始めた。続きの区切りで、まとめて作らせる
            self._set_thinking(False)   # 頼んだ返事は取り消される。アプリの「考えています」を消す
            if self.backchannel is not None:
                self.backchannel.stop()
            if self._started_at is None:
                self._started_at = ev.created_at
            if self.backchannel is not None and self.nod and (self._watch is None or self._watch.done()):
                self._watch = asyncio.create_task(self._watch_pauses())
        elif ev.new_state == 'listening' and ev.old_state == 'speaking':
            self._speaking = False
            self._ended_at = ev.created_at
            if self._segment_start is not None:
                seg = Segment(self._segment_start, ev.created_at,
                              self._start_judging(self._segment_start, ev.created_at),
                              self.history.reserve(self._segment_start) if self.history is not None else None)
                self._segments.append(seg)   # 文字起こしと組にする
                self._recent.append(seg)     # 返事を作らせるときに使う
                self._segment_start = None
            if self._pending:
                self._reply_later(STALE_SECONDS)

    def take_segment(self, started_at: float | None = None) -> 'Segment | None':
        """発言開始時刻で区間を選ぶ。時刻を取得できない場合は未対応の古い区間を使う。"""
        now = time.time()
        self._segments = [s for s in self._segments if now - s.end < SEGMENT_KEEP_SECONDS]
        if started_at is not None:
            # LiveKit のユーザー会話項目には、API が通知した実際の発言開始時刻が付く。
            # 書き起こしが逆順に届いても、その発言の声・話者と組にする。
            segment = min(self._segments, key=lambda s: abs(s.start - started_at), default=None)
            if segment is not None and abs(segment.start - started_at) < 0.5:
                self._segments.remove(segment)
                return segment
            return None  # 対応が不明な発言に、別の人の声を付けない
        return self._segments.pop(0) if self._segments else None

    async def speaker_of(self, segment: 'Segment | None') -> 'speakers.Judgment | None':
        """その区間の判定（話し終わりに 1 回だけ決めたもの。シエルへの [発言者：…] と同じ）。無ければ None"""
        if segment is None or segment.judgment is None:
            return None
        return await segment.judgment

    def _start_judging(self, start: float, end: float) -> 'asyncio.Task | None':
        """話し終わった区間の声で、誰が話したかを裏で決め始める（返事と文字起こしの両方が、この結果を使う）"""
        if self.book is None or self.encoder is None:
            return None
        t = asyncio.create_task(self._judge(start, end))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def _judge(self, start: float, end: float) -> 'speakers.Judgment | None':
        seconds, pending = self._embed(start, end)
        try:
            e = await pending if pending is not None else None
        except Exception:
            log.exception('発言の声の特徴を計算できない')
            return None
        await self.book.refresh()
        j = self.book.judge(e, seconds)
        self.style.on_voices(len(self.book.speakers))   # ひかえめで返事をしないときも、ほかの人の声に気づく
        return j

    async def _judgment_for(self, start: float, end: float) -> 'speakers.Judgment | None':
        """返事を作らせる発言（start〜end。区切りが続いた発言は、いくつかの区間をまとめたもの）の判定。
        話者が分かった区間のうち、一番新しいものを使う（「シエル、」のような短い区間は不明になるので）。
        区間がまだ無いとき（話し終わりの知らせより先に返事を作らせた）は、その場で決める"""
        segs = [s for s in self._recent if start - 0.01 <= s.start and s.end <= end + 0.01 and s.judgment is not None]
        if not segs:
            return await self._judge(start, end)
        judgments = [await s.judgment for s in segs]
        return next((j for j in reversed(judgments) if j is not None and j.sp is not None), judgments[-1])

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
        await asyncio.sleep(settle)   # 待つあいだに、話者の判定は裏で進んでいる（_start_judging）
        if self._speaking:
            return
        self._early = None
        self._forget()
        await self._reply(start, end)

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

    async def _reply(self, start: float, end: float) -> None:
        if self.book is not None:
            self.book.current_turns = []
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
            await self._generate_reply(extra)
            return
        t0 = time.perf_counter()
        j = await self._judgment_for(start, end)
        self.book.current_turns = [s.turn for s in self._recent
                                   if start - 0.01 <= s.start and s.end <= end + 0.01 and s.turn is not None]
        if not self.book.current_turns and self.history is not None:
            self.book.current_turns = [t for t in self.history.turns if t.role == 'user' and start <= t.at <= end]
        presence = self.style.presence
        parts = await self.book.identify_parts(j, solo=presence == 'solo', push_notes=presence in ('solo', 'close'))
        line = None
        if parts is not None:
            tag, memory = parts
            if TURN_CONTEXT == 'items' and await self._add_context(tag):
                line = memory or None   # 話者の行は会話に置いた。メモ・関係だけ返事ごとの指示に足す
            else:
                line = tag + memory
        if self.book.last is not None:
            self.book.last_at = time.monotonic()   # 最後に話した人を、触った人とみなせる時間（touch.py）
        log.info('話者の判定 %.0f ms（声 %.1f 秒）', (time.perf_counter() - t0) * 1000, j.seconds if j else 0.0)
        touch = self.touch.take() if self.touch is not None else None
        if touch is not None:
            extra['user_input'] = touch
        if line is not None:
            extra['instructions'] = '\n\n'.join(filter(None, (extra.get('instructions'), line)))
        latency.mark('返事を頼んだ')
        await self._generate_reply(extra)

    async def _generate_reply(self, extra: dict) -> None:
        if self.minutes is not None:
            context = self.minutes.context()
            if TURN_CONTEXT == 'items':
                # 議事録の状態は、変わったときだけ会話の後ろに置く（足せなかったら、今回の指示に足す）
                if context != self._minutes_context and await self._add_context(context):
                    self._minutes_context = context
                elif context != self._minutes_context:
                    extra['instructions'] = '\n\n'.join(filter(None, (extra.get('instructions'), context)))
            else:
                extra['instructions'] = '\n\n'.join(filter(None, (extra.get('instructions'), context)))
        self.session.generate_reply(**extra)
        self._set_thinking(True)

    def _set_thinking(self, on: bool) -> None:
        """アプリに、返事を考えているか（返事を頼んでから声が出るまで）を知らせる。LiveKit の lk.agent.state は、
        Realtime API と自前の読み上げの組み合わせでは thinking を通らない（listening から speaking へ直接変わる）ので、自分で送る。
        アプリは、声が出るか（speaking）、取り消しの知らせ（on=false）か、6 秒たつまで「考えています…」と出す"""
        if not on and not self._thinking:
            return   # 知らせていないのに、取り消しだけ送らない（「考えています」は毎回送る）
        self._thinking = on
        publish = getattr(self.style, 'publish', None)
        if publish is not None:
            publish({'v': 1, 'type': 'agent.thinking', 'on': on})

    async def _add_context(self, text: str) -> bool:
        """会話の後ろ（相手の発言のすぐ後ろ）に、会話モデルへの補足を system の項目として 1 つ置く（TURN_CONTEXT=items）。
        置いたと確かめる返事（1 往復、約 0.12 秒）は待たない。LiveKit は項目を作る知らせを送ってから確認を待つので、
        送るところまで進めてから返事を頼めば、同じ接続の上で「項目を作る → 返事を作る」の順に届く（2026-10-22、bench_latency.py）。
        すぐに失敗したときだけ False（呼んだ側が、今までどおり返事ごとの指示に足す）。あとから断られたら、ログに残す"""
        agent = getattr(self.session, 'current_agent', None)
        if agent is None:
            return False
        try:
            ctx = agent.chat_ctx.copy()
            ctx.add_message(role='system', content=text)
        except Exception as e:
            log.warning('会話に補足を置けない（返事ごとの指示に足す）: %s', e)
            return False
        # LiveKit は、手元の会話と会話モデルの側の会話の差を送る。会話モデルの側にだけある項目（まだ手元に届いていない
        # 相手の発言など）があると、それを消してしまうので、そのときは置かない
        remote = getattr(agent, 'realtime_llm_session', None)
        if remote is not None:
            try:
                local_ids = {item.id for item in ctx.items}
                if any(item.id not in local_ids for item in remote.chat_ctx.items):
                    log.info('会話モデルの側の会話が手元にまだ届いていないので、補足は返事ごとの指示に足す')
                    return False
            except Exception as e:   # 会話モデルの側の会話を読めない（会話の始まる前など）
                log.warning('会話モデルの側の会話を読めない（返事ごとの指示に足す）: %s', e)
                return False
        task = asyncio.create_task(agent.update_chat_ctx(ctx))
        self._tasks.add(task)
        task.add_done_callback(self._context_done)
        await asyncio.sleep(0)   # 項目を作る知らせを送るところまで進める
        if task.done() and not task.cancelled() and task.exception() is not None:
            return False
        latency.mark('補足を置いた')
        debug_log.record('context_item', text=text)
        return True

    def _context_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.warning('会話に置いた補足が断られた: %s', task.exception())
