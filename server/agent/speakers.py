# -*- coding: utf-8 -*-
"""話者の識別：多人数の会話で、発言ごとに「誰が話したか」を声の特徴（ECAPA-TDNN）で判定する。

- 会議の声は 1 本に混ざって届く。会話モデル（Realtime API）には今までどおり声を渡し、発言が終わったら、
  その発言の声の特徴を計算して、覚えている人（speaker_store、PostgreSQL＋pgvector）と、この会話で聞いた人と比べる。
- 結果は「[発言者：田中]」「[発言者：たぶん田中]」「[発言者：知らない人A]」「[発言者：不明]」の 1 行にして、
  会話モデルへ渡す（agent.py が返事を作らせる前に足す）。
- 名前を付ける・覚える・忘れるのは、会話モデルが道具（agent.py の name_speaker・forget_speaker）を呼んだとき。
  覚える（DB に保存する）のは、本人が同意したときだけ。知らない人の声の特徴は、この会話の間だけメモリーに持つ。
- 声の特徴は 192 次元のベクトル（録音そのものではない）。それでも個人を識別できる情報なので、名前や特徴をログに出さない。
  決めたことは docs/decisions/speaker-identification-ja.md。
"""
import asyncio
import collections
import logging
import os
import string
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from livekit import rtc

import relationship
from jst import JST

log = logging.getLogger('ciel-agent.speakers')

SR = 16000
BUFFER_SECONDS = 30          # 発言の声を取り出すために、届いた声をためておく長さ
LEAD_SECONDS = 0.8           # 「話し始めた」の知らせは実際より遅れて届くので、少し前から取る
MAX_SECONDS = 8.0            # 長い発言は最後の 8 秒だけ使う（計算を軽くする）
MIN_VOICED = float(os.environ.get('CIEL_SPK_MIN_SECONDS', '1.0'))   # これより短い発言は「不明」
# コサイン類似度の基準（Zoom を通した声で測って決める。docs/decisions/speaker-identification-ja.md）
MATCH = float(os.environ.get('CIEL_SPK_MATCH', '0.45'))   # この会話で聞いた（まだ覚えていない）人は、これ以上なら同じ人
# 覚えている人は、これ以上なら「確か」（メモの元にしてよい）。0.45 では、覚えている人しかいない会話の最初に、
# ほかの人の発言が 0.47 で「確か」になった（2026-10-18）。本人は 0.60〜0.88 だった
SURE = float(os.environ.get('CIEL_SPK_SURE', '0.55'))
MAYBE = float(os.environ.get('CIEL_SPK_MAYBE', '0.35'))   # これ以上なら「たぶん」（覚えている人も、この会話の人も）
ADAPT = float(os.environ.get('CIEL_SPK_ADAPT', '0.60'))   # これ以上なら、覚えている人の見本に足す
MAX_SESSION_EMBEDDINGS = 20
MAX_ADAPT_PER_SESSION = 3
SPLIT_BONUS = 0.05          # 人違いだと言われて分けた人を、元の人より少し優先する
PUSH_NOTES = 15             # 2 人のとき、本人だと分かったら渡すメモの数（最近の分）
MARGIN = float(os.environ.get('CIEL_SPK_MARGIN', '0.05'))   # 次に近い人との差がこれ未満なら「たぶん」
MODEL = 'speechbrain/spkrec-ecapa-voxceleb'
MODEL_REVISION = '0f99f2d0ebe89ac095bcc5903c4dd8f72b367286'   # Dockerfile と同じ版
MODEL_DIR = os.environ.get('CIEL_ECAPA_DIR', '/opt/ecapa')


class Encoder:
    """ECAPA-TDNN（SpeechBrain、spkrec-ecapa-voxceleb、Apache-2.0）。CPU で動かす。プロセスごとに 1 回読み込む。"""

    _instance: 'Encoder | None' = None

    def __init__(self) -> None:
        import torch
        from speechbrain.inference.speaker import EncoderClassifier
        torch.set_num_threads(int(os.environ.get('CIEL_SPK_THREADS', '4')))
        self._torch = torch
        # モデルはイメージを作るときに取ってある（Dockerfile。起動のたびに取りに行かない：HF_HUB_OFFLINE=1）
        self._model = EncoderClassifier.from_hparams(source=MODEL, revision=MODEL_REVISION, savedir=MODEL_DIR,
                                                     run_opts={'device': 'cpu'})

    @classmethod
    def get(cls) -> 'Encoder':
        if cls._instance is None:
            t0 = time.perf_counter()
            cls._instance = Encoder()
            log.info('ECAPA を読み込んだ（%.1f 秒）', time.perf_counter() - t0)
        return cls._instance

    def embed(self, audio: np.ndarray) -> np.ndarray:
        """16 kHz・float32 の声 → 長さ 1 の 192 次元ベクトル"""
        with self._torch.inference_mode():
            e = self._model.encode_batch(self._torch.from_numpy(audio[None, :]))
        v = e.reshape(-1).numpy().astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)


class AudioTap:
    """会議の声（Unity が送るマイクのトラック）を、会話モデルとは別に受けてためておく。"""

    def __init__(self) -> None:
        self._chunks: collections.deque[tuple[float, np.ndarray]] = collections.deque()
        self._task: asyncio.Task | None = None

    def attach(self, track: rtc.Track) -> None:
        if self._task is not None:
            self._task.cancel()
        self._chunks.clear()
        self._task = asyncio.create_task(self._read(rtc.AudioStream(track, sample_rate=SR, num_channels=1)))

    async def _read(self, stream: rtc.AudioStream) -> None:
        async for ev in stream:
            now = time.time()
            self._chunks.append((now, np.frombuffer(ev.frame.data, dtype=np.int16).copy()))
            while self._chunks and now - self._chunks[0][0] > BUFFER_SECONDS:
                self._chunks.popleft()

    def window(self, start: float, end: float) -> np.ndarray:
        """start〜end（time.time()）に届いた声。float32"""
        parts = [c for t, c in self._chunks if start <= t <= end]
        if not parts:
            return np.zeros(0, np.float32)
        return np.concatenate(parts).astype(np.float32) / 32768.0


def voiced(audio: np.ndarray) -> np.ndarray:
    """声のある 20 ms だけを残す（無音や小さな雑音で、声の特徴がぼやけないように）"""
    n = SR // 50
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if len(frames) == 0:
        return audio
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
    keep = db > max(-50.0, db.max() - 30.0)
    out = frames[keep].reshape(-1)
    return out[-int(MAX_SECONDS * SR):]


@dataclass
class Known:
    person_id: int
    name: str
    embeddings: list[np.ndarray]
    last_seen: datetime | None = None   # この会話より前に、最後に話した日時
    disputed: bool = False              # この会話で人違いだと言われた（見本を足さない）
    notes_ok: bool = False              # お話（メモ）を覚える同意があるか
    note_count: int = 0                 # メモの数


def jst(t: datetime) -> str:
    t = t.astimezone(JST)
    return f'{t.month}月{t.day}日'


def plain_name(name: str) -> str:
    """敬称を外した名前（「ハカセさん」→「ハカセ」）"""
    name = name.strip()
    for s in ('さん', 'ちゃん', 'くん', '君', '様'):
        if name.endswith(s) and len(name) > len(s):
            return name[: -len(s)].strip()
    return name


@dataclass
class SessionSpeaker:
    label: str                       # 会話モデルに見せる呼び名（知らない人A、または名前）
    embeddings: list[np.ndarray] = field(default_factory=list)
    person_id: int | None = None     # 覚えている人なら DB の番号
    name: str | None = None
    announced: bool = False          # 前に話した日を、この会話で伝えたか
    notes_pushed: bool = False       # その人のメモを、この会話で会話モデルに渡したか
    relation_pushed: bool = False    # シエルとその人との関係を、この会話で会話モデルに渡したか
    split: bool = False              # 人違いだと言われて、ほかの人から分けた人
    speaker_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    notes_context: str = ''
    relation_context: dict[bool, str] = field(default_factory=dict)
    memory_suppressed: bool = False

    def add(self, e: np.ndarray) -> None:
        self.embeddings.append(e)
        del self.embeddings[:-MAX_SESSION_EMBEDDINGS]


@dataclass
class Judgment:
    """発言 1 つの、誰が話したかの判定（SpeakerBook.judge）。シエルへの [発言者：…] と記録係が同じものを使う"""
    sp: SessionSpeaker | None            # 話した人。None は「不明」（短い・声の特徴が無い）
    sure: bool                           # 確かか（False は「たぶん」）
    e: np.ndarray | None = None          # 声の特徴（人違いを直すとき・見本に足すときに使う）
    seconds: float = 0.0                 # 声のある長さ
    score: float = -1.0                  # 類似度


@dataclass
class NameRegistration:
    name: str
    source: str
    introduced_by: str | None = None
    registration_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    speaker_id: str | None = None
    stage: str = 'pending_identity'

    def view(self) -> dict:
        return {'registration_id': self.registration_id, 'proposed_name': self.name,
                'source': self.source, 'introduced_by': self.introduced_by,
                'bound_speaker_id': self.speaker_id, 'registration_state': self.stage}


def best_score(e: np.ndarray, embeddings: list[np.ndarray]) -> float:
    """見本の中で似ている上位 3 つの平均（見本が 1 つなら、それとの類似度）"""
    if not embeddings:
        return -1.0
    s = np.sort(np.stack(embeddings) @ e)[::-1]
    return float(s[:3].mean())


class SpeakerBook:
    """この会話の話者の帳簿。覚えている人（DB）は会話の始めに読み込み、照合はメモリーの中で行う。"""

    def __init__(self, store) -> None:
        self.store = store                    # speaker_store.Store。DB が無ければ None（この会話の間だけ覚える）
        self.known: list[Known] = []
        self.speakers: list[SessionSpeaker] = []
        self.last: SessionSpeaker | None = None
        self.last_at = -1e9   # 最後に話した人が話した時刻（time.monotonic。turns.py が付ける。touch.py が使う）
        self._unknown_count = 0
        self._adapted = 0
        self.last_embedding: np.ndarray | None = None   # 直前の発言の声の特徴（人違いを直すとき使う）
        self.last_sure = False                           # 直前の発言者を、自信を持って判定したか（メモを読むときに使う）
        self.on_notes_consent = None   # お話を覚えることに同意したとき呼ぶ（notes.NoteTaker.on_consent。agent.py がつなぐ）
        self.on_split = None           # 人違いを直したとき呼ぶ（conversation.Conversation.on_split）
        self.last_rows: list[int] = []                   # 直前の発言で DB に足した見本の行
        self._identity_lock = asyncio.Lock()
        self.name_registrations: dict[str, NameRegistration] = {}  # この接続だけの仮名簿、最大64件
        self.current_turns: list = []  # この返答の元発言。本人訂正の確認に使う（本文はログに出さない）
        self._versions: dict[int, int] = {}
        self._shared_available = True

    async def load(self) -> None:
        if self.store is not None:
            self.known = [Known(pid, name, embs, seen, disputed=False, notes_ok=ok, note_count=n)
                          for pid, name, embs, seen, ok, n in await self.store.load_all()]
        log.info('覚えている人：%d 人', len(self.known))

    async def refresh(self) -> None:
        """Refresh committed shared memory before judging a turn, without sharing conversation history."""
        if self.store is None or not hasattr(self.store, 'versions'):
            return
        async with self._identity_lock:
            try:
                versions = await self.store.versions()
                self._shared_available = True
                if versions == self._versions:
                    return
                changed = {pid for pid in versions.keys() | self._versions.keys()
                           if versions.get(pid) != self._versions.get(pid)}
                old = {k.person_id: k for k in self.known}
                rows = await self.store.load_all()
                self.known = [Known(pid, name, embs, old[pid].last_seen if pid in old else seen,
                                    disputed=old[pid].disputed if pid in old else False, notes_ok=ok, note_count=n)
                              for pid, name, embs, seen, ok, n in rows]
                live = {k.person_id: k for k in self.known}
                for sp in self.speakers:
                    pid = sp.person_id
                    if pid is None or pid not in changed:
                        continue
                    sp.notes_pushed, sp.notes_context = False, ''
                    sp.relation_context.clear()
                    if pid not in live:
                        sp.person_id, sp.name = None, None
                        sp.memory_suppressed = True
                        for entry in self.name_registrations.values():
                            if entry.speaker_id == sp.speaker_id:
                                entry.speaker_id, entry.stage = None, 'pending_identity'
                    else:
                        sp.name = live[pid].name
                        snapshot = await self.store.memory_snapshot(pid)
                        sp.memory_suppressed = snapshot is None or snapshot['blocked'] or not snapshot['consent']
                        for entry in self.name_registrations.values():
                            if entry.speaker_id == sp.speaker_id:
                                entry.name = sp.name
                self._versions = versions
            except Exception as e:
                self._versions = {}
                self._shared_available = False
                for sp in self.speakers:
                    sp.notes_context = ''
                    sp.notes_pushed = False
                    sp.relation_context.clear()
                    sp.memory_suppressed = True
                log.warning('共有記憶を更新できない error=%s', type(e).__name__)

    def _new_unknown_label(self) -> str:
        i = self._unknown_count
        self._unknown_count += 1
        letters = string.ascii_uppercase
        return '知らない人' + (letters[i] if i < 26 else str(i + 1))

    def _scores(self, e: np.ndarray) -> tuple[float, 'Known | None', float, 'SessionSpeaker | None', float]:
        """覚えている人と、この会話で聞いた（まだ覚えていない）人を、まとめて比べる。
        （一番近い覚えている人の類似度とその人、一番近いこの会話の人の類似度とその人、覚えている人の次点の類似度）。
        人違いだと言われて分けた人（split）は、声が似ているので、元の人より少し優先する。
        次点は、似た声の人との差が小さいときに断定しないために使う"""
        known = sorted(((best_score(e, k.embeddings), k) for k in self.known), key=lambda x: -x[0])
        session = sorted(((best_score(e, s.embeddings) + (SPLIT_BONUS if s.split else 0.0), s)
                          for s in self.speakers if s.person_id is None), key=lambda x: -x[0])
        k_score, k = known[0] if known else (-1.0, None)
        s_score, s = session[0] if session else (-1.0, None)
        runner_up = max(known[1][0] if len(known) > 1 else -1.0, s_score)
        return k_score, k, s_score, s, runner_up

    def _session_for(self, k: 'Known') -> SessionSpeaker:
        """覚えている人の、この会話での話者（無ければ作る）"""
        sp = next((s for s in self.speakers if s.person_id == k.person_id), None)
        if sp is None:
            sp = SessionSpeaker(label=k.name, person_id=k.person_id, name=k.name)
            self.speakers.append(sp)
        return sp

    def judge(self, e: np.ndarray | None, seconds: float) -> 'Judgment':
        """発言 1 つ（話し始め〜話し終わりの区間）の声で、誰が話したかを 1 回だけ決める（turns.py が話し終わりに呼ぶ）。
        この結果を、シエルへの「[発言者：…]」（identify）と、メモの記録係・議事録の係（文字起こしの話者）の両方に使う
        （別々に計算すると、同じ発言でも食い違うことがあったため。2026-10-18）。
        - この会話で聞いた人（まだ覚えていない人）：MATCH 以上なら同じ人。MAYBE 以上なら「たぶん」その人（新しい人を作らない）。
        - 覚えている人：SURE 以上で、次に近い人との差が MARGIN 以上なら「確か」。MAYBE 以上なら「たぶん」。
        - どちらにも近くなければ、初めての声として、この会話の知らない人を作る。
        - 短い・声の特徴が無い発言は「不明」（sp が None）。"""
        if e is None or seconds < MIN_VOICED:
            log.info('話者：短い発言（声 %.1f 秒）', seconds)
            return Judgment(None, False, e, seconds)
        k_score, k, s_score, s, runner_up = self._scores(e)
        if s is not None and s_score >= MAYBE and s_score >= k_score:
            sure = s_score >= MATCH
            if sure:
                s.add(e)   # 「たぶん」の声は見本に足さない（別の人の声が混ざらないように）
            log.info('話者：この会話の %s（%.2f%s）', '名前を聞いた人' if s.name else s.label, s_score,
                     '' if sure else '、たぶん')
            return Judgment(s, sure, e, seconds, s_score)
        if k is not None and k_score >= MAYBE:
            sure = k_score >= SURE and k_score - runner_up >= MARGIN
            sp = self._session_for(k)
            sp.add(e)
            log.info('話者：覚えている人 #%d（%.2f、次点との差 %.2f%s）', k.person_id, k_score, k_score - runner_up,
                     '' if sure else '、たぶん')
            return Judgment(sp, sure, e, seconds, k_score)
        sp = SessionSpeaker(label=self._new_unknown_label())
        sp.add(e)
        self.speakers.append(sp)
        log.info('話者：初めての声 → %s（一番近い %.2f）', sp.label, max(k_score, s_score))
        return Judgment(sp, True, e, seconds, max(k_score, s_score))

    @staticmethod
    def label(j: 'Judgment | None') -> str:
        """記録係・議事録の係に渡す話者の呼び名（シエルへの [発言者：…] と同じ言葉）"""
        if j is None or j.sp is None:
            return '不明'
        name = j.sp.name or j.sp.label
        return name if j.sure else 'たぶん' + name

    async def identify(self, j: 'Judgment | None', solo: bool = False, push_notes: bool = False) -> str | None:
        """発言の判定（judge の結果）から、会話モデルに渡す 1 行を作る。None は「何も足さない」。
        solo（ふたりきり）のとき、短くて判定できない発言は、直前の人のままとみなして何も足さない
        （「不明」を渡すと、シエルが声の判定のことを話してしまうので）。
        push_notes のとき、本人のメモを渡す（その場にいる人が、ひとり・身近な人のとき。mode.py）。
        この会話でまだ渡していなければ、途中で渡せるようになったときにも渡す。"""
        await self.refresh()
        if j is None or j.sp is None:
            if solo:
                return None
            self.last = None
            return '[発言者：不明]'
        e, sp, sure, score, seconds = j.e, j.sp, j.sure, j.score, j.seconds
        self.last_embedding, self.last_rows, self.last_sure = e, [], False
        self.last = sp
        k = next((k for k in self.known if k.person_id == sp.person_id), None) if sp.person_id is not None else None
        if k is None:
            # この会話で聞いた、まだ覚えていない人（判定のあとで名前を聞いた人も）
            self.last_sure = sure
            return self._session_tag(sp, sure)
        if not self._shared_available:
            self.last_sure = sure
            return f'[発言者：{k.name}（保存情報は現在確認できないため、以前のメモは使わない）]'

        # 覚えている人
        if (sure and score >= ADAPT and seconds >= 2.0 and not k.disputed
                and self._adapted < MAX_ADAPT_PER_SESSION and self.store):
            # よく当たった声を見本に足して、マイクや部屋が変わっても当たるようにしていく
            # （人違いだと言われたら、split で消せるように、足した行を覚えておく）
            self._adapted += 1
            k.embeddings.append(e)
            self.last_rows = await self.store.add_voiceprints(k.person_id, [e], seconds)
        if self.store:
            await self.store.touch(k.person_id)
        self.last_sure = sure
        if not sure:
            return f'[発言者：たぶん{k.name}（声を覚えている人）]'
        snapshot = None
        if self.store is not None and hasattr(self.store, 'memory_snapshot'):
            snapshot = await self.store.memory_snapshot(k.person_id)
            if snapshot is None or snapshot['blocked'] or not snapshot['consent']:
                sp.memory_suppressed = True
                sp.notes_context = ''
                sp.relation_context.clear()
        extra, memory = '', ''
        first = not sp.announced
        if first:
            # この会話で初めて分かったときだけ、前に話した日と、同意のことを添える（本人が話しているときだけ）
            sp.announced = True
            if k.last_seen is not None:
                extra += f'。前に話したのは{jst(k.last_seen)}'
            if not k.notes_ok:
                extra += '。お話を覚える同意はまだ'
        if k.notes_ok and k.note_count and push_notes and not sp.notes_pushed and not sp.memory_suppressed and self.store is not None:
            # ひとり・身近な人のときは、本人のメモ（最近の分だけ）を渡す。どう使うかは presence_*.md。
            # 人前のときは渡さない（話題にすると、ほかの人に伝わる）。聞かれたら道具で読む
            rows = (snapshot['notes'] if snapshot is not None else await self.store.notes(k.person_id))[-PUSH_NOTES:]
            today = datetime.now(JST).strftime('%Y-%m-%d')
            sp.notes_context = (f'\n[{k.name}さんについて覚えていること（今日は{today}）：'
                      + '／'.join(t for _, t in rows) + ']')
            sp.notes_pushed = True
            log.info('話者：#%d のメモ %d 件を会話モデルに渡した', k.person_id, len(rows))
        elif first and k.notes_ok and k.note_count and not push_notes:
            extra += '。この人について覚えていることがある'
        memory = sp.notes_context if push_notes and not sp.memory_suppressed else ''
        if k.notes_ok and not sp.memory_suppressed and self.store is not None:
            # シエルがその人をどう思っているか（relationship.py）。話し方の下敷きにする。
            # 人前では、口調のための段階だけ（気持ちの中身は、ほかの人に伝わるので渡さない）
            if push_notes not in sp.relation_context:
                sp.relation_context[push_notes] = relationship.context(
                    k.name, snapshot['relationship'] if snapshot is not None else await self.store.relationship(k.person_id),
                    k.last_seen, private=push_notes)
            sp.relation_pushed = True
            memory += sp.relation_context[push_notes]
        return f'[発言者：{k.name}（声を覚えている人{extra}）]{memory}'

    async def split(self, name: str = '') -> str:
        """人違いを直す：直前の発言を、判定された人から外し、別の人としてこの会話で区別する。
        以後、その人の発言は分けた人の見本に入っていく（split の人は少し優先して照合する）。"""
        sp, e = self.last, self.last_embedding
        if sp is None or e is None:
            return '直前の発言の声が分からないので、分けられません。もう一度、少し長めに話してもらってください。'
        if sp.person_id is None and sp.name is None:
            return f'直前の発言は、まだ誰とも判定していません（{sp.label}）。お名前を聞いて name_speaker を使ってください。'
        old = sp.name or sp.label
        sp.embeddings = [x for x in sp.embeddings if x is not e]
        if sp.person_id is not None:
            k = next((k for k in self.known if k.person_id == sp.person_id), None)
            if k is not None:
                k.embeddings = [x for x in k.embeddings if x is not e]
                k.disputed = True   # この会話では、この人の見本を足さない（似た声が混ざらないように）
            if self.last_rows and self.store is not None:
                await self.store.delete_voiceprints(self.last_rows)   # 間違って足した見本を消す
        new_name = plain_name(name) if name.strip() else None
        new = SessionSpeaker(label=new_name or self._new_unknown_label(), name=new_name, split=True)
        new.add(e)
        self.speakers.append(new)
        self.last, self.last_rows = new, []
        if self.on_split:
            self.on_split(sp, new)
        log.info('話者：人違いを直した（%s から分けた）', '覚えている人 #%d' % sp.person_id if sp.person_id else 'この会話の人')
        if new_name:
            return (f'わかりました。直前の発言は{old}さんではなく、{new_name}さんとして区別します'
                    '（この会話の間。声はまだ保存していません）。声を覚えてよいか聞いてください。')
        return f'わかりました。直前の発言は{old}さんではない、別の方として区別します（呼び名：{new.label}）。お名前を聞いてください。'

    @staticmethod
    def _session_tag(sp: 'SessionSpeaker', sure: bool = True) -> str:
        """まだ声を覚えていない人。名前を聞いたかどうかも伝える（覚えている人と区別できるように）。
        似た声で自信がなければ「たぶん」を付ける"""
        maybe = '' if sure else 'たぶん'
        if sp.name:
            return f'[発言者：{maybe}{sp.name}（名前はこの会話の間だけ。声は覚えていない）]'
        return f'[発言者：{maybe}{sp.label}（まだ名前を知らない人）]'

    def find(self, label: str) -> SessionSpeaker | None:
        label = label.strip().strip('[]').replace('発言者：', '').removeprefix('たぶん').split('（')[0]
        label = plain_name(label)
        matches = [s for s in self.speakers if label in (s.label, s.name, s.speaker_id)]
        return matches[0] if len(matches) == 1 else None

    async def speaker_status(self, sp: SessionSpeaker | None = None) -> dict:
        sp = sp or self.last
        if sp is None:
            return {'status': 'no_speaker', 'available': True, 'identity_certain': False,
                    'storage_available': self.store is not None,
                    'name_registrations': [r.view() for r in self.name_registrations.values()]}
        state = {'status': 'ok', 'available': True, 'speaker_id': sp.speaker_id, 'name': sp.name,
                 'session_label': sp.label, 'identity_certain': self.last is sp and self.last_sure,
                 'storage_available': self.store is not None, 'name_scope': 'session' if sp.name else 'unknown',
                 'name_saved': False, 'voice_saved': False, 'voice_sample_count': 0, 'notes_consented': False}
        state['name_registrations'] = [r.view() for r in self.name_registrations.values()
                                       if r.speaker_id is None or r.speaker_id == sp.speaker_id]
        if sp.person_id is not None:
            if self.store is None:
                return {**state, 'status': 'storage_unavailable', 'name_saved': None, 'voice_saved': None}
            try:
                saved = await self.store.identity(sp.person_id)
            except Exception as e:
                log.warning('話者：保存状態を確認できない error=%s', type(e).__name__)
                return {**state, 'status': 'storage_error', 'name_saved': None, 'voice_saved': None}
            if saved is not None:
                state.update(name=saved['name'], name_scope='persistent', name_saved=True,
                             voice_saved=saved['voice_sample_count'] > 0,
                             voice_sample_count=saved['voice_sample_count'], notes_consented=saved['notes_consented'])
        return state

    def roster(self) -> dict:
        return {'scope': 'current_session', 'registrations': [r.view() for r in self.name_registrations.values()],
                'heard_speakers': [{'speaker_id': s.speaker_id, 'name': s.name, 'label': s.label}
                                   for s in self.speakers]}

    def _propose_name(self, name: str, self_introduction: bool) -> tuple[NameRegistration | None, str]:
        name = plain_name(name)
        if not name or len(name) > 100:
            return None, 'invalid_name'
        current = self.last.speaker_id if self.last is not None else None
        source = 'self' if self_introduction else 'introduced'
        if self_introduction:
            matches = [r for r in self.name_registrations.values() if r.name == name and (
                r.speaker_id is None or (current is not None and r.speaker_id == current))]
        else:
            matches = [r for r in self.name_registrations.values() if r.name == name
                       and r.source == source and current is not None and r.introduced_by == current]
        if len(matches) > 1:
            return None, 'ambiguous_name'
        if matches:
            return matches[0], 'ok'
        if len(self.name_registrations) >= 64:
            return None, 'registration_limit'
        entry = NameRegistration(name, source, None if self_introduction else current)
        self.name_registrations[entry.registration_id] = entry
        return entry, 'ok'

    async def register_name(self, name: str, self_introduction: bool = False, *, confirm_identity: bool = True) -> dict:
        async with self._identity_lock:
            entry, status = self._propose_name(name, self_introduction)
            if entry is None:
                return {'status': status}
            if self_introduction and confirm_identity:
                return await self._confirm_name(entry, name, False)
            return {'status': entry.stage, **entry.view()}

    async def confirm_name(self, registration_id: str, confirmed_name: str, remember: bool = False) -> dict:
        async with self._identity_lock:
            entry = self.name_registrations.get(registration_id)
            if entry is None:
                return {'status': 'registration_not_found', 'scope': 'current_session'}
            return await self._confirm_name(entry, confirmed_name, remember)

    async def _confirm_name(self, entry: NameRegistration, confirmed_name: str, remember: bool) -> dict:
        info = entry.view()
        if plain_name(confirmed_name) != entry.name:
            return {'status': 'name_mismatch', **info}
        sp = self.last
        if sp is None or not self.last_sure:
            return {'status': 'pending_identity', **info, 'identity_certain': False}
        if entry.source == 'introduced' and entry.introduced_by == sp.speaker_id:
            return {'status': 'introduced_person_must_confirm', **info}
        if entry.speaker_id is not None and entry.speaker_id != sp.speaker_id:
            return {'status': 'not_current_speaker', **info}
        if sp.name is not None and plain_name(sp.name) != entry.name:
            return {'status': 'name_conflict', **info}
        # 先に会話中の本人対応を確定する。DB保存の失敗でこの確認まで失わない。
        result = await self._name(sp.speaker_id, entry.name, False)
        if result['status'] in ('session_named', 'already_named', 'already_saved'):
            entry.speaker_id = sp.speaker_id
            entry.stage = 'saved' if result.get('voice_saved') and result.get('name_saved') else 'session_named'
            if remember:
                result = await self._name(sp.speaker_id, entry.name, True)
                if result.get('voice_saved') and result.get('name_saved'):
                    entry.stage = 'saved'
        if 'name_registrations' in result:
            result['name_registrations'] = [r.view() for r in self.name_registrations.values()
                                            if r.speaker_id is None or r.speaker_id == sp.speaker_id]
        return {**result, **entry.view()}

    async def name(self, label: str, name: str, remember: bool) -> dict:
        async with self._identity_lock:
            return await self._name(label, name, remember)

    async def _name(self, label: str, name: str, remember: bool) -> dict:
        sp = self.find(label) if label else self.last
        name = plain_name(name)
        if not name or len(name) > 100:
            return {'status': 'invalid_name'}
        if sp is None:
            if not label and not remember:
                entry, status = self._propose_name(name, True)
                return {'status': 'pending_identity', **entry.view()} if entry else {'status': status}
            return {'status': 'speaker_not_found' if label else 'no_speaker'}
        if sp is not self.last:
            return {'status': 'not_current_speaker', 'speaker_id': sp.speaker_id}
        if not self.last_sure:
            if not remember:
                entry, status = self._propose_name(name, True)
                return {'status': 'pending_identity', **entry.view()} if entry else {'status': status}
            return {'status': 'identity_uncertain', 'speaker_id': sp.speaker_id}
        if sp.person_id is not None and sp.name is not None and plain_name(sp.name) != name:
            return {'status': 'name_conflict', 'speaker_id': sp.speaker_id}
        current = await self.speaker_status(sp)
        if current['status'] in ('storage_error', 'storage_unavailable'):
            return current
        if current['voice_saved']:
            return {**current, 'status': 'already_saved'}
        if current['name_saved'] and not remember:
            return {**current, 'status': 'already_named'}
        sp.name = name  # 発言者の固定ラベル・IDは変えない
        if not remember:
            return {**await self.speaker_status(sp), 'status': 'session_named'}
        if self.store is None:
            return {**await self.speaker_status(sp), 'status': 'storage_unavailable'}
        if not sp.embeddings:
            return {**await self.speaker_status(sp), 'status': 'need_voice_sample'}
        try:
            pid = await self.store.remember_person(name, list(sp.embeddings), sp.person_id)
        except Exception as e:
            log.warning('話者：名前と声を保存できない error=%s', type(e).__name__)
            return {**await self.speaker_status(sp), 'status': 'save_failed'}
        sp.person_id = pid  # コミットが成功してからメモリーも更新する
        if not any(k.person_id == pid for k in self.known):
            self.known.append(Known(pid, name, []))
        k = next(k for k in self.known if k.person_id == sp.person_id)
        k.name = name
        new = [e for e in sp.embeddings if not any(e is x for x in k.embeddings)]
        k.embeddings.extend(new)
        # 覚えてよいかの質問は「お名前と声、それからお話も少し」なので、メモを残す同意も一緒にもらっている
        k.notes_ok = True
        if self.on_notes_consent:
            try:
                self.on_notes_consent(sp.person_id)
            except Exception as e:
                log.warning('話者：保存後のメモ通知に失敗 error=%s', type(e).__name__)
        if self.last is sp:
            self.last_sure = True   # 本人が同意したので、この会話ではメモを読み書きしてよい
        log.info('話者：#%d として声を覚えた（見本 %d）', sp.person_id, len(new))
        state = await self.speaker_status(sp)
        if state['name_saved'] and state['voice_saved']:
            for entry in self.name_registrations.values():
                if entry.speaker_id == sp.speaker_id:
                    entry.stage = 'saved'
        return {**state, 'status': 'saved' if state['name_saved'] and state['voice_saved'] else 'save_unverified'}

    # ---- その人について覚えておくメモ（読むのは本人が話しているときだけ。書くのは notes.py が裏で） ----

    def current_person(self) -> 'Known | None':
        """いま話している人が、自信を持って判定した「覚えている人」なら、その人"""
        sp = self.last
        if sp is None or sp.person_id is None or not self.last_sure:
            return None
        return next((k for k in self.known if k.person_id == sp.person_id), None)

    async def agree_notes(self) -> str:
        k = self.current_person()
        if k is None or self.store is None:
            return 'いま話している方が、声を覚えている方だと確かではないので、受け付けられません。'
        await self.store.set_notes_consent(k.person_id)
        k.notes_ok = True
        if self.on_notes_consent:
            self.on_notes_consent(k.person_id)
        log.info('話者：#%d がお話を覚えることに同意した', k.person_id)
        return f'{k.name}さんのお話を、少しずつ覚えていきます。'

    async def recall(self) -> str:
        await self.refresh()
        k = self.current_person()
        if k is None or self.store is None:
            return 'いま話している方が誰か確かではないので、覚えていることは読めません。'
        if not k.notes_ok:
            return f'{k.name}さんからは、お話を覚える同意をまだもらっていません。'
        if hasattr(self.store, 'memory_snapshot'):
            snapshot = await self.store.memory_snapshot(k.person_id)
            if snapshot is None or not snapshot['consent']:
                return '保存された記憶を確認できません。'
            if snapshot['blocked']:
                return '忘れる依頼を処理中なので、以前のメモは読みません。'
            rows, r = snapshot['notes'], snapshot['relationship']
        else:
            rows = await self.store.notes(k.person_id)
            r = await self.store.relationship(k.person_id)
        feeling = (f'\nシエルの{k.name}さんへの気持ち（{relationship.STAGES[r.stage]}）：{r.feeling}'
                   if r is not None and r.feeling else '')
        if not rows:
            return f'{k.name}さんについて、まだ覚えていることはありません。' + feeling
        return (f'{k.name}さんについて覚えていること：\n' + '\n'.join(f'{n}. {t}' for n, (_, t) in enumerate(rows, 1))
                + feeling)

    async def rename(self, new_name: str) -> str:
        async with self._identity_lock:
            return await self._rename(new_name)

    async def _rename(self, new_name: str) -> str:
        """呼び名を直す（聞き間違えたとき、呼び方を変えてほしいとき）。直せるのは、いま話している本人の呼び名だけ"""
        sp = self.last
        if sp is None or not self.last_sure:
            return '呼び名を直せるのは、ご本人が話しているときだけです。直したい方ご本人に、もう一度言ってもらってください。'
        if sp.name is None:
            return 'まだお名前を聞いていない方です。name_speaker で名前を付けてください。'
        old, new = sp.name, plain_name(new_name)
        if not new or new == old:
            return f'呼び名は「{old}」のままです。'
        if sp.person_id is None:
            sp.name = new
            sp.notes_pushed, sp.notes_context = False, ''
            sp.relation_context.clear()
            for entry in self.name_registrations.values():
                if entry.speaker_id == sp.speaker_id:
                    entry.name = new
            return f'呼び名を「{old}」から「{new}」に直しました（この会話の間だけ。声は保存していません）。'
        if self.store is not None:
            await self.store.rename(sp.person_id, new)
        else:
            return '記録の場所が使えないので、保存済みの呼び名は変更できません。'
        sp.name = new
        sp.notes_pushed, sp.notes_context = False, ''
        sp.relation_context.clear()
        for entry in self.name_registrations.values():
            if entry.speaker_id == sp.speaker_id:
                entry.name = new
        for k in self.known:
            if k.person_id == sp.person_id:
                k.name = new
        log.info('話者：#%d の呼び名を直した', sp.person_id)
        return f'呼び名を「{old}」から「{new}」に直しました。次の会話からも「{new}」さんです。'

    def lookup(self, name: str) -> str:
        """その名前の人を覚えているか。前に話した日は、本人が話しているときだけ教える"""
        name = plain_name(name)
        k = next((k for k in self.known if k.name == name), None)
        if k is not None:
            if self.last is not None and self.last.person_id == k.person_id and k.last_seen is not None:
                return f'{name}さんの声を覚えています（いま話しているのは{name}さん）。前に話したのは {jst(k.last_seen)}。'
            return f'{name}さんの声を覚えています。'
        if any(s.name == name for s in self.speakers):
            return f'{name}さんは、この会話の間だけ名前を聞いている人です（声は保存していません）。'
        return f'{name}さんの声は覚えていません。'

    def here(self) -> str:
        """この会話で声を聞いた人の呼び名"""
        if not self.speakers:
            return 'この会話では、まだ誰の声も区別していません。'
        parts = [(s.name or s.label) + ('（声を覚えている人）' if s.person_id is not None else '') for s in self.speakers]
        return 'この会話で声を聞いた人：' + '、'.join(parts)

    async def forget(self, name: str) -> str:
        async with self._identity_lock:
            return await self._forget(name)

    async def _forget(self, name: str) -> str:
        """本人の依頼のときだけ：直前の発言者が、その名前の覚えている人であること"""
        sp = self.last
        if sp is None or not self.last_sure or sp.person_id is None or plain_name(name) not in (sp.name, sp.label):
            return 'ご本人からの依頼のときだけ消せます。消したい方ご本人に、もう一度お願いしてもらってください。'
        pid = sp.person_id
        if self.store is not None:
            await self.store.delete_person(pid)
        self.known = [k for k in self.known if k.person_id != pid]
        self.speakers.remove(sp)
        for entry in self.name_registrations.values():
            if entry.speaker_id == sp.speaker_id:
                entry.speaker_id, entry.stage = None, 'pending_identity'
        self.last = None
        log.info('話者：#%d の声の記録を消した', pid)
        return f'「{name}」さんの声の記録を消しました。'
