# -*- coding: utf-8 -*-
"""話者の識別：多人数の会話で、発言ごとに「誰が話したか」を声の特徴（ECAPA-TDNN）で判定する。

- 会議の声は 1 本に混ざって届く。会話モデル（Realtime API）には今までどおり声を渡し、発言が終わったら、
  その発言の声の特徴を計算して、覚えている人（speaker_store、PostgreSQL＋pgvector）と、この会話で聞いた人と比べる。
- 結果は「[発言者：田中]」「[発言者：たぶん田中]」「[発言者：知らない人A]」「[発言者：不明]」の 1 行にして、
  会話モデルへ渡す（agent.py が返事を作らせる前に足す）。
- 名前を付ける・覚える・忘れるのは、会話モデルが道具（agent.py の name_speaker・forget_speaker）を呼んだとき。
  覚える（DB に保存する）のは、本人が同意したときだけ。知らない人の声の特徴は、この会話の間だけメモリーに持つ。
- アプリの参加者パネルへ、名簿と最後に話した人を知らせる（state、topic ciel.event の speakers.state）。
  アプリからは、この会話の間だけの名前・同じ人にまとめる・人違いを分けるができる（on_data、topic ciel.speakers）。
  保存（DB）に触れる操作は、アプリからはできない（端末の持ち主にする・やめる と、まとめた声を覚えている人の見本に足すことだけ）。
- 端末の持ち主：アプリで「この端末の持ち主」にした覚えている人。アプリは接続のたびに端末の ID と合言葉を送り（hello）、
  会話サーバーは合言葉のハッシュで持ち主を確かめる。その場にいる人がひとり・身近な人のときは、持ち主の声を優先して当てる
  （初めの数回の発言で「知らない人」にならないように）。この経路（端末）で当たった声は、経路の印を付けて見本に足す。
- 人違いからの回復：この会話の知らない人の声が、何回か分まとめて覚えている人に近ければ、その人だったとまとめる。
- 長い会議で人を増やしすぎない：だれにも似ていない短めの声と、まだ出ていない覚えている人に「たぶん」似ただけの声は保留にし、
  似た声がもう一度来たら参加者にする。知らない人どうしの声が近づいたら、同じ人にまとめ直す。
- 声の特徴は 192 次元のベクトル（録音そのものではない）。それでも個人を識別できる情報なので、名前や特徴をログに出さない。
  決めたことは docs/decisions/speaker-identification-ja.md。
"""
import asyncio
import collections
import hashlib
import json
import logging
import os
import re
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
# これより短い発言では、人を決めない（新しい人を作らない）。1.0 秒では「私は田中です」も無音を除くと届かず、
# 複数人のときに名乗りが「不明」になって、名前の確認・同意が進まなかった（2026-10-25）
MIN_VOICED = float(os.environ.get('CIEL_SPK_MIN_SECONDS', '0.8'))
# MIN_VOICED より短い返事（「いいよ」「はい」）は、これ以上あれば声の特徴を取り、直前の人と同じかだけを確かめる（_judge_short）
SHORT_VOICED = float(os.environ.get('CIEL_SPK_SHORT_SECONDS', '0.3'))
# 短い返事が「ほかの人の声だ」と言える類似度（直前の人より MARGIN 以上近いことも要る）。短い声（0.4〜0.7 秒）は、
# 会話サーバーで同じ声どうしでも 0.18〜0.26 にしかならず（2026-10-25、読み上げの声を 1 回で作って切り分けて流した）、
# 声で本人を確かめることはできない。なので、ほかの人だとはっきり分かるときだけ断り、それ以外は直前の人の返事とみなす
SHORT_MATCH = float(os.environ.get('CIEL_SPK_SHORT_MATCH', '0.35'))
SHORT_WITHIN = 30.0   # 直前の人が話してからこの秒数を過ぎた短い発言は、返事とみなさない
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
APP_TOPIC = 'ciel.speakers'   # アプリの参加者パネルからの直し
# 端末の持ち主（ひとり・身近な人のとき）。別の経路で録った見本とは 0.4〜0.5 くらいにしかならないことがあるので、
# 持ち主だけは低めでも「たぶん持ち主」にして、知らない人を作らない。「確か」（メモを渡す）は高めのまま
OWNER_MAYBE = float(os.environ.get('CIEL_SPK_OWNER_MAYBE', '0.30'))
OWNER_SURE = float(os.environ.get('CIEL_SPK_OWNER_SURE', '0.50'))
OWNER_ADAPT = float(os.environ.get('CIEL_SPK_OWNER_ADAPT', '0.50'))
OWNER_BONUS = 0.10          # この会話の人・ほかの覚えている人より、これだけ低くても「たぶん持ち主」にする
MAX_OWNER_ADAPT = 6         # 持ち主は、この経路の見本を早く集める
# 人違いからの回復：この会話の知らない人の、最近の発言の声をまとめて、覚えている人と比べる
RECOVER = float(os.environ.get('CIEL_SPK_RECOVER', '0.50'))
RECOVER_OWNER = float(os.environ.get('CIEL_SPK_RECOVER_OWNER', '0.42'))   # ひとり・身近な人のときの持ち主
RECOVER_MIN = 3             # まとめて比べる発言の数（これより少なければ比べない）
RECOVER_RECENT = 5
# まだこの会話に出ていない覚えている人にまとめるときは、高めにする（その場にいない人にまとめないように。2026-10-26）
RECOVER_ABSENT = float(os.environ.get('CIEL_SPK_RECOVER_ABSENT', '0.55'))
# 保留の声：だれにも似ていない声で、新しい人をすぐには作らない（長い会議で知らない人が 30 人ほどに増えた。2026-10-26）。
# 笑い声・小声・声の重なり・物音で、同じ人でも類似度が下がった発言のたびに、新しい人ができていた
NEW_SECONDS = float(os.environ.get('CIEL_SPK_NEW_SECONDS', '2.5'))   # 声がこれ以上あれば、1 回で新しい人にする
PENDING_SECONDS = 300.0     # 保留の声を持っておく秒数
MAX_PENDING = 20
# 知らない人どうしのまとめ直し：声の平均どうしがこれ以上なら同じ人とみなす
REGROUP = float(os.environ.get('CIEL_SPK_REGROUP', '0.55'))
GREETING_NOTES = 5          # あいさつに添える、持ち主について覚えていることの数（最近の分）
MERGE_PRINTS = 3            # アプリで覚えている人にまとめたとき、DB の見本に足す数
DEVICE_ID = re.compile(r'^[A-Za-z0-9_-]{8,64}$')
# 声の登録（アプリの「声を登録する」。画面の文を読んでもらい、その声で見本を作る。_enroll_judge）
ENROLL_NEEDED = 4            # 受け付ける読み上げの数
ENROLL_MIN_SECONDS = 1.2     # これより短い読み上げは、もう一度読んでもらう
ENROLL_SAME = float(os.environ.get('CIEL_SPK_ENROLL_SAME', '0.35'))   # これまでの読み上げとこれ未満なら、別の人の声とみなす
ENROLL_TIMEOUT = 180.0       # 始めてからこの秒数で、終わっていなければやめる
ENROLL_GAP = 1.2             # 前の読み上げからこの秒数以内に始まった発言は、同じ文の続き


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
        self.listeners: list = []   # 届いた声を順に渡す先（時刻, int16）。歌を聴いているあいだの singing.py

    def attach(self, track: rtc.Track) -> None:
        if self._task is not None:
            self._task.cancel()
        self._chunks.clear()
        self._task = asyncio.create_task(self._read(rtc.AudioStream(track, sample_rate=SR, num_channels=1)))

    async def _read(self, stream: rtc.AudioStream) -> None:
        async for ev in stream:
            now = time.time()
            pcm = np.frombuffer(ev.frame.data, dtype=np.int16).copy()
            self._chunks.append((now, pcm))
            for listener in self.listeners:
                listener(now, pcm)
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

    def notes(self) -> list[str]:
        """この会話で渡してよいことになった、その人について覚えていること（notes_context の中身。無ければ空）。
        notes_context は、その場にいる人がひとり・身近な人で、本人の同意があるときだけ作られる（identify_parts）"""
        if self.memory_suppressed or '：' not in self.notes_context:
            return []
        body = self.notes_context.split('：', 1)[1].rstrip().rstrip(']')
        return [n for n in body.split('／') if n.strip()]

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
    owner: bool = False                  # 端末の持ち主として当てた（ひとり・身近な人のとき）
    short: bool = False                  # 短い返事で、直前の人と同じかだけを確かめた（_judge_short）
    enroll: bool = False                 # 声の登録の読み上げ（返事をしない・メモの元にしない）
    pending: 'PendingVoice | None' = None   # 保留の声（だれにも決めなかった。sp は None）


@dataclass
class PendingVoice:
    """保留の声：人を決めなかった発言の声。似た声がもう一度来たら、その人を参加者にする"""
    e: np.ndarray
    seconds: float
    at: float                            # time.monotonic
    person_id: int | None = None         # まだこの会話に出ていない覚えている人に「たぶん」似ていた（その人の番号）


@dataclass
class Enrollment:
    """声の登録の途中（アプリの「声を登録する」）。名前と同意は、アプリの画面で本人が入れて押したもの"""
    name: str
    sp: 'SessionSpeaker'                 # 登録する人（この会話での話者）
    person_id: int | None = None         # 覚えている人の声を足すとき
    embeddings: list = field(default_factory=list)
    readings: int = 0                    # 受け付けた文の数（1 つの文が区切られても 1 つ）
    last_at: float = 0.0                 # 最後に受け付けた時刻（time.monotonic、判定したとき）
    status: str = 'listening'            # listening・short・other_voice・saving・saved・failed・cancelled・timeout
    started: float = field(default_factory=time.monotonic)


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
        self.pending: list[PendingVoice] = []   # 保留の声（参加者にも議事録にも出さない）
        self.pending_last: PendingVoice | None = None   # 直前の発言が保留の声なら、それ（名乗ったときに人を作る）
        self.last_embedding: np.ndarray | None = None   # 直前の発言の声の特徴（人違いを直すとき使う）
        self.recent: SessionSpeaker | None = None   # 最後に分かった話者と、その確かさ（短い返事を比べる相手）
        self.recent_sure = False
        self.recent_at = -1e9
        self.last_short = False
        self.last_sure = False                           # 直前の発言者を、自信を持って判定したか（メモを読むときに使う）
        self.on_notes_consent = None   # お話を覚えることに同意したとき呼ぶ（notes.NoteTaker.on_consent。agent.py がつなぐ）
        self.on_split = None           # 人違いを直したとき呼ぶ（conversation.Conversation.on_split）
        self.last_rows: list[int] = []                   # 直前の発言で DB に足した見本の行
        self._identity_lock = asyncio.Lock()
        self.name_registrations: dict[str, NameRegistration] = {}  # この接続だけの仮名簿、最大64件
        self.current_turns: list = []  # この返答の元発言。本人訂正の確認に使う（本文はログに出さない）
        self._versions: dict[int, int] = {}
        self._shared_available = True
        self.on_change = None          # 名簿・最後に話した人が変わったとき呼ぶ（引数は state()。agent.py がアプリへ送る）
        self.on_merge = None           # アプリで同じ人にまとめたとき呼ぶ（conversation.Conversation.on_merge）
        self.heard: Judgment | None = None   # 最後に判定した発言（アプリで光らせる人）
        self._heard_count = 0
        self._published: dict | None = None
        self._app_tasks: set[asyncio.Task] = set()
        self.private = None            # その場にいる人がひとり・身近な人か（引数なしで呼ぶ。agent.py がつなぐ）
        self.owner_id: int | None = None   # 端末の持ち主（覚えている人の番号。アプリの hello で決まる）
        self.channel: str | None = None    # 声の経路（端末ごと。見本に印を付ける）
        self.device_known = asyncio.Event()   # アプリの hello を受け取った（あいさつの前に、持ち主が分かるのを少し待つ）
        self.enrolling: Enrollment | None = None   # 声の登録の途中（その間は返事をしない。turns.py・initiative.py が見る）
        self.on_enroll = None          # 登録の様子が変わったとき呼ぶ（引数は enroll_state()。agent.py がアプリへ送る）
        self.on_enrolled = None        # 登録できたとき呼ぶ（引数は名前。agent.py がシエルにひとこと言わせる）

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
                if self.owner_id is not None and self.owner_id not in live:
                    self.owner_id = None
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
                self.notify()
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
        j = self._enroll_judge(e, seconds) if self.enrolling is not None else self._judge(e, seconds)
        self.pending_last = j.pending
        if j.sp is not None:   # 短くて分からない発言では、光らせる人を変えない
            self.heard = j
            self._heard_count += 1
        self.notify()
        return j

    def _judge(self, e: np.ndarray | None, seconds: float) -> 'Judgment':
        """発言 1 つ（話し始め〜話し終わりの区間）の声で、誰が話したかを 1 回だけ決める（turns.py が話し終わりに呼ぶ）。
        この結果を、シエルへの「[発言者：…]」（identify）と、メモの記録係・議事録の係（文字起こしの話者）の両方に使う
        （別々に計算すると、同じ発言でも食い違うことがあったため。2026-10-18）。
        - この会話で聞いた人（まだ覚えていない人）：MATCH 以上なら同じ人。MAYBE 以上なら「たぶん」その人（新しい人を作らない）。
        - 覚えている人：SURE 以上で、次に近い人との差が MARGIN 以上なら「確か」。MAYBE 以上なら「たぶん」。
          まだこの会話に出ていない人は、「確か」か、「たぶん」が 2 回あったときだけ参加者にする（1 回目は保留）。
        - どちらにも近くなければ初めての声。NEW_SECONDS 以上の声か、まだだれもいないときは、この会話の知らない人を作る。
          それより短ければ保留にして、似た声がもう一度来たら知らない人を作る。
        - 短い・声の特徴が無い発言・保留の声は「不明」（sp が None）。"""
        if e is None or seconds < SHORT_VOICED:
            log.info('話者：短い発言（声 %.1f 秒）', seconds)
            return Judgment(None, False, e, seconds)
        if seconds < MIN_VOICED:
            return self._judge_short(e, seconds)
        k_score, k, s_score, s, runner_up = self._scores(e)
        owner = self._owner_judge(e, seconds, s_score, s)
        if owner is not None:
            return owner
        if s is not None and s_score >= MAYBE and s_score >= k_score:
            sure = s_score >= MATCH
            if sure:
                s.add(e)   # 「たぶん」の声は見本に足さない（別の人の声が混ざらないように）
                s = self._regroup(s)
                recovered = self._recover(s)
                if recovered is not None:
                    dst, score, rsure = recovered
                    return Judgment(dst, rsure, e, seconds, score, owner=dst.person_id == self.owner_id)
            log.info('話者：この会話の %s（%.2f%s）', '名前を聞いた人' if s.name else s.label, s_score,
                     '' if sure else '、たぶん')
            return Judgment(s, sure, e, seconds, s_score)
        self._drop_old_pending()
        if k is not None and k_score >= MAYBE:
            sure = k_score >= SURE and k_score - runner_up >= MARGIN
            here = any(x.person_id == k.person_id for x in self.speakers)
            before = None
            if not here and not sure:
                # まだこの会話に出ていない人に「たぶん」似ているだけ。その場にいない人を参加者にしないように、
                # 前にも「たぶん」その人だった保留の声があるときだけ参加者にする
                before = next((p for p in reversed(self.pending) if p.person_id == k.person_id), None)
                if before is None:
                    p = self._hold(e, seconds, k.person_id)
                    log.info('話者：まだ出ていない覚えている人 #%d に、たぶん似ている（%.2f）→ 保留', k.person_id, k_score)
                    return Judgment(None, False, e, seconds, k_score, pending=p)
                self.pending.remove(before)
            sp = self._session_for(k)
            if before is not None:
                sp.add(before.e)
            sp.add(e)
            log.info('話者：覚えている人 #%d（%.2f、次点との差 %.2f%s%s）', k.person_id, k_score, k_score - runner_up,
                     '' if sure else '、たぶん', '、2 回目なので参加者にした' if before is not None else '')
            return Judgment(sp, sure, e, seconds, k_score)
        best = max(k_score, s_score)
        if seconds < NEW_SECONDS and self.speakers:
            # 短めの初めての声は、外れた声（笑い声・小声・声の重なり・物音）かもしれない。似た保留の声があれば新しい人にする
            scored = [(float(p.e @ e), p) for p in self.pending]
            score, before = max(scored, key=lambda x: x[0], default=(-1.0, None))
            if before is None or score < MATCH:
                p = self._hold(e, seconds)
                log.info('話者：初めての声（声 %.1f 秒、一番近い %.2f）→ 保留', seconds, best)
                return Judgment(None, False, e, seconds, best, pending=p)
            self.pending.remove(before)
            sp = self._new_speaker([before.e, e])
            log.info('話者：保留の声に似た声（%.2f）→ %s', score, sp.label)
            return Judgment(sp, True, e, seconds, best)
        sp = self._new_speaker([e])
        log.info('話者：初めての声 → %s（一番近い %.2f）', sp.label, best)
        return Judgment(sp, True, e, seconds, best)

    def _new_speaker(self, embeddings: list[np.ndarray]) -> SessionSpeaker:
        sp = SessionSpeaker(label=self._new_unknown_label())
        for x in embeddings:
            sp.add(x)
        self.speakers.append(sp)
        return sp

    def _hold(self, e: np.ndarray, seconds: float, person_id: int | None = None) -> PendingVoice:
        p = PendingVoice(e, seconds, time.monotonic(), person_id)
        self.pending.append(p)
        del self.pending[:-MAX_PENDING]
        return p

    def _drop_old_pending(self) -> None:
        now = time.monotonic()
        self.pending = [p for p in self.pending if now - p.at <= PENDING_SECONDS]

    def _promote_pending(self) -> None:
        """直前の発言が保留の声で、その人が名乗った：その声で、この会話の知らない人を作る（名前を付けられるように）。
        短い返事や、まだ出ていない覚えている人に似ていた声からは作らない"""
        p = self.pending_last
        if p is None or self.last is not None or p.person_id is not None or p.seconds < MIN_VOICED:
            return
        self.pending_last = None
        if p in self.pending:
            self.pending.remove(p)
        sp = self._new_speaker([p.e])
        self.last, self.last_sure, self.last_short, self.last_embedding, self.last_rows = sp, True, False, p.e, []
        self.recent, self.recent_sure, self.recent_at = sp, True, time.monotonic()
        log.info('話者：保留の声の人が名乗ったので %s にした', sp.label)
        self.notify()

    @staticmethod
    def _centroid(sp: SessionSpeaker) -> np.ndarray:
        c = np.mean(np.stack(sp.embeddings), axis=0)
        return c / (np.linalg.norm(c) + 1e-9)

    def _regroup(self, sp: SessionSpeaker) -> SessionSpeaker:
        """知らない人どうしのまとめ直し：sp の声の平均が、ほかの知らない人の声の平均に近ければ、同じ人としてまとめる
        （一度ふたりに分かれた人が、話すほど似てきたとき）。名前の違う人どうし・人違いだと言われて分けた人はまとめない。
        残った人を返す"""
        if sp.person_id is not None or sp.split or not sp.embeddings:
            return sp
        c = self._centroid(sp)
        scored = sorted(((float(self._centroid(t) @ c), t) for t in self.speakers
                         if t is not sp and t.person_id is None and not t.split and t.embeddings
                         and (t.name is None or sp.name is None or plain_name(t.name) == plain_name(sp.name))),
                        key=lambda x: -x[0])
        if not scored or scored[0][0] < REGROUP:
            return sp
        score, t = scored[0]
        # 名前を聞いた人か、先に聞いた人のほうに残す
        first = self.speakers.index(t) < self.speakers.index(sp)
        dst, src = (t, sp) if (t.name is not None or (sp.name is None and first)) else (sp, t)
        log.info('話者：知らない人どうしの声が近いので、まとめた（%.2f）', score)
        self._merge(src, dst)
        return dst

    # ---- 声の登録（アプリの「声を登録する」。docs/speaker-recognition-research-ja.md の案 A） ----

    def enroll_state(self) -> dict:
        en = self.enrolling
        return {'v': 1, 'type': 'enroll.state', 'active': en is not None and en.status not in ('saved', 'failed'),
                'name': en.name if en else '', 'speaker_id': en.sp.speaker_id if en else '',
                'accepted': en.readings if en else 0, 'needed': ENROLL_NEEDED, 'status': en.status if en else ''}

    def _enroll_notify(self) -> None:
        if self.on_enroll is not None:
            try:
                self.on_enroll(self.enroll_state())
            except Exception:
                log.exception('話者：登録の様子をアプリへ知らせられない')

    def _enroll_start(self, speaker_id, name) -> str:
        """登録を始める。名前と同意は、本人がアプリの画面で入れて押したもの。
        声を覚えている人の声を足すのは、その人が直前に確かに話したときだけ（ほかの人の声を足さないように）"""
        if self.store is None:
            return 'storage_unavailable'
        if self.enrolling is not None:
            return 'already_enrolling'
        sp = self._by_id(speaker_id) if speaker_id else None
        if speaker_id and sp is None:
            return 'speaker_not_found'
        person_id = None
        if sp is not None and sp.person_id is not None:
            if sp is not self.last or not self.last_sure:
                return 'not_current_speaker'
            person_id, name = sp.person_id, sp.name or name
        name = plain_name(name) if isinstance(name, str) else ''
        if not name or len(name) > 40:
            return 'invalid_name'
        if sp is None:
            sp = SessionSpeaker(label=self._new_unknown_label())
            self.speakers.append(sp)
        self.enrolling = Enrollment(name, sp, person_id)
        log.info('話者：声の登録を始めた（%s）', '覚えている人 #%d' % person_id if person_id else 'まだ覚えていない人')
        self._enroll_notify()
        return 'enrolling'

    def _enroll_cancel(self, status: str = 'cancelled') -> str:
        en = self.enrolling
        if en is None:
            return 'not_enrolling'
        en.status = status
        self._enroll_notify()
        self.enrolling = None
        if not en.sp.embeddings and en.sp.person_id is None and en.sp in self.speakers:
            self.speakers.remove(en.sp)   # 1 回も読まなかった人の札は残さない
        log.info('話者：声の登録をやめた（%s）', status)
        return status

    def _enroll_judge(self, e: np.ndarray | None, seconds: float) -> 'Judgment':
        """登録の途中の発言：読み上げとして受け付ける。短い発言はもう一度読んでもらう。これまでの読み上げ（すでに声を
        聞いている人なら、その声）と違う声は、別の人の声として受け付けない。返事はしない（enroll）"""
        en = self.enrolling
        if time.monotonic() - en.started > ENROLL_TIMEOUT:
            self._enroll_cancel('timeout')
            return self._judge(e, seconds)
        if en.status == 'saving':
            return Judgment(None, False, e, seconds, enroll=True)
        if e is None or seconds < ENROLL_MIN_SECONDS:
            # 文の切れ端（「シエル、」のように、文の途中で区切られたもの）。知らせずに読み流す
            return Judgment(None, False, e, seconds, enroll=True)
        reference = en.embeddings or (en.sp.embeddings if en.person_id is None else [])
        score = best_score(e, reference) if reference else 1.0
        if score < ENROLL_SAME:
            en.status = 'other_voice'
            log.info('話者：登録の読み上げが、これまでと違う声（%.2f）', score)
            self._enroll_notify()
            return Judgment(None, False, e, seconds, score, enroll=True)
        now = time.monotonic()
        # 1 つの文が、途中の息つぎで 2〜3 個に区切られることがある（2026-10-25、開発用の試験）。前に受け付けた読み上げの
        # すぐあと（ENROLL_GAP 秒以内）に始まったものは、同じ文の続きとして、声は見本に足し、数は増やさない
        same_reading = en.readings > 0 and now - seconds - en.last_at < ENROLL_GAP
        en.embeddings.append(e)
        en.sp.add(e)
        en.last_at = now
        if not same_reading:
            en.readings += 1
        en.status = 'listening'
        log.info('話者：登録の読み上げ %d/%d（声 %.1f 秒、%.2f%s）', en.readings, ENROLL_NEEDED, seconds, score,
                 '、同じ文の続き' if same_reading else '')
        if en.readings >= ENROLL_NEEDED:
            en.status = 'saving'
            task = asyncio.get_running_loop().create_task(self._enroll_save())
            self._app_tasks.add(task)
            task.add_done_callback(self._app_tasks.discard)
        self._enroll_notify()
        return Judgment(en.sp, True, e, seconds, score, enroll=True)

    async def _enroll_save(self) -> None:
        """読み上げた声で、名前と声を保存する（同意はアプリの画面で取った。お話のメモの同意も含む文面）。
        同じ名前の覚えている人がいれば、声が近いときだけその人に足す（別の人が名前を名乗って声を足さないように）"""
        en = self.enrolling
        status = 'failed'
        try:
            async with self._identity_lock:
                pid = en.person_id
                if pid is None:
                    same = next((k for k in self.known if k.name == en.name), None)
                    if same is not None:
                        score = float(np.mean([best_score(x, same.embeddings) for x in en.embeddings]))
                        if score < ENROLL_SAME:
                            raise LookupError('name_taken')
                        pid = same.person_id
                if pid is not None:
                    await self.store.add_voiceprints(pid, list(en.embeddings), None, channel=self.channel)
                    k = next((k for k in self.known if k.person_id == pid), None)
                    if k is not None:
                        k.embeddings.extend(en.embeddings)
                        k.disputed = False
                    en.sp.person_id, en.sp.name = pid, k.name if k is not None else en.name
                else:
                    pid = await self.store.remember_person(en.name, list(en.embeddings), None, channel=self.channel)
                    self.known.append(Known(pid, en.name, list(en.embeddings), notes_ok=True))
                    en.sp.person_id, en.sp.name = pid, en.name
                    if self.on_notes_consent:
                        self.on_notes_consent(pid)
                self.last, self.last_sure, self.last_short = en.sp, True, False
                self.recent, self.recent_sure, self.recent_at = en.sp, True, time.monotonic()
                status = 'saved'
                log.info('話者：声の登録で #%d の声を覚えた（見本 %d）', pid, len(en.embeddings))
        except LookupError:
            status = 'name_taken'
        except Exception as ex:
            log.warning('話者：声の登録を保存できない error=%s', type(ex).__name__)
        en.status = status
        self._enroll_notify()
        self.enrolling = None
        self.notify()
        if status == 'saved' and self.on_enrolled is not None:
            try:
                self.on_enrolled(en.sp.name or en.name)
            except Exception:
                log.exception('話者：登録できたことをシエルに伝えられない')

    def debug_scores(self, e: np.ndarray) -> dict[str, float]:
        """調べるとき（デバッグ用の会話ログ）：この会話の人・覚えている人それぞれとの類似度"""
        out = {(s.name or s.label): round(best_score(e, self._voice_of(s)), 3) for s in self.speakers if self._voice_of(s)}
        out.update({k.name: round(best_score(e, k.embeddings), 3) for k in self.known
                    if k.embeddings and not any(s.person_id == k.person_id for s in self.speakers)})
        return out

    def _voice_of(self, sp: 'SessionSpeaker') -> list[np.ndarray]:
        """その人の声の見本（この会話の声と、覚えている人なら DB の見本）"""
        k = next((k for k in self.known if k.person_id == sp.person_id), None) if sp.person_id is not None else None
        return sp.embeddings + (k.embeddings if k is not None else [])

    def _judge_short(self, e: np.ndarray, seconds: float) -> 'Judgment':
        """短い返事（「いいよ」「はい」）：直前に話した人（SHORT_WITHIN 秒以内）の返事とみなし、直前の判定の確かさを
        引き継ぐ（名乗った人に「覚えていい？」と聞いた返事を、その人の同意として受け付けられるように。2026-10-25 まで、
        短い返事は「不明」になり、複数人のときに同意が受け付けられず聞き直しが続いた）。
        短い声では本人かを確かめられないので、ほかの人の声だとはっきり分かるときだけ「不明」にする。
        新しい人は作らず、見本にも足さない"""
        last = self.recent
        if last is not None and time.monotonic() - self.recent_at > SHORT_WITHIN:
            last = None   # 直前の人が話してから時間がたった（返事ではない）
        if last is None or not self._voice_of(last):
            log.info('話者：短い発言（声 %.1f 秒。比べる直前の人がいない）', seconds)
            return Judgment(None, False, e, seconds, short=True)
        score = best_score(e, self._voice_of(last))
        others = [best_score(e, self._voice_of(s)) for s in self.speakers if s is not last and self._voice_of(s)]
        others += [best_score(e, k.embeddings) for k in self.known
                   if k.person_id != last.person_id and not any(s.person_id == k.person_id for s in self.speakers)]
        other = max(others, default=-1.0)
        if other >= SHORT_MATCH and other - score >= MARGIN:
            log.info('話者：短い発言（声 %.1f 秒。直前の人 %.2f、ほかの人 %.2f）→ ほかの人の声なので不明', seconds, score, other)
            return Judgment(None, False, e, seconds, score, short=True)
        log.info('話者：短い発言は直前の人の返事とみなす（声 %.1f 秒、%.2f、ほかの人 %.2f）', seconds, score, other)
        return Judgment(last, self.recent_sure, e, seconds, score, short=True)

    def _is_private(self) -> bool:
        try:
            return bool(self.private and self.private())
        except Exception:
            return False

    def _owner(self) -> 'Known | None':
        """ひとり・身近な人のときの、端末の持ち主（人違いだと言われていなければ）"""
        if self.owner_id is None or not self._is_private():
            return None
        return next((k for k in self.known if k.person_id == self.owner_id and not k.disputed), None)

    def _owner_judge(self, e: np.ndarray, seconds: float, s_score: float,
                     s: 'SessionSpeaker | None') -> 'Judgment | None':
        """端末の持ち主を優先して当てる。ほかの人（この会話の人・覚えている人）より OWNER_BONUS 低くても「たぶん持ち主」。
        「確か」は OWNER_SURE 以上で、ほかの人より MARGIN 以上近いときだけ（メモを渡すので、家族などを取り違えない）。
        人違いだと言われて分けた人がよく当たるなら、持ち主にしない"""
        owner = self._owner()
        if owner is None or (s is not None and s.split and s_score >= MATCH):
            return None
        o_score = best_score(e, owner.embeddings)
        other = max([s_score] + [best_score(e, x.embeddings) for x in self.known if x is not owner])
        if o_score < OWNER_MAYBE or o_score + OWNER_BONUS < other:
            return None
        sure = o_score >= OWNER_SURE and o_score - other >= MARGIN
        sp = self._session_for(owner)
        sp.add(e)
        log.info('話者：端末の持ち主（%.2f、ほかとの差 %.2f%s）', o_score, o_score - other, '' if sure else '、たぶん')
        return Judgment(sp, sure, e, seconds, o_score, owner=True)

    def _recover(self, sp: 'SessionSpeaker') -> 'tuple[SessionSpeaker, float, bool] | None':
        """この会話の知らない人が、実は覚えている人だったら、その人にまとめる（一度「知らない人」になると、
        その人の新しい声のほうが覚えている見本より近くなり、ずっと知らない人のままになっていた。2026-10-24）。
        最近の発言の声をまとめて比べる（1 回分より確か）。会議などで、その覚えている人がこの会話ですでに別に話して
        いるなら、まとめない（似た声の別の人）。まだこの会話に出ていない人には、高め（RECOVER_ABSENT）でないとまとめない
        （その場にいない人にしないように）。ひとり・身近な人のときの持ち主は、少し低くてもまとめる"""
        if sp.person_id is not None or sp.name is not None or sp.split or len(sp.embeddings) < RECOVER_MIN:
            return None
        recent = sp.embeddings[-RECOVER_RECENT:]
        private = self._is_private()
        heard = {s.person_id for s in self.speakers if s.person_id is not None and s.embeddings}
        scored = sorted(((float(np.mean([best_score(x, k.embeddings) for x in recent])), k)
                         for k in self.known if not k.disputed and k.embeddings), key=lambda x: -x[0])
        if not scored:
            return None
        score, k = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else -1.0
        owner = private and k.person_id == self.owner_id
        need = RECOVER_OWNER if owner else RECOVER if k.person_id in heard else max(RECOVER, RECOVER_ABSENT)
        if (score < need or score - runner_up < MARGIN
                or (k.person_id in heard and not private)):
            return None
        dst = self._session_for(k)
        self._merge(sp, dst)
        sure = score >= (OWNER_SURE if owner else SURE)
        log.info('話者：知らない人の声が覚えている人 #%d に近いので、まとめた（%.2f、%d 回分）', k.person_id, score, len(recent))
        return dst, score, sure

    @property
    def owner_name(self) -> str:
        return next((k.name for k in self.known if k.person_id == self.owner_id), '') if self.owner_id is not None else ''

    async def greeting_context(self, private: bool) -> str:
        """会話の始めのあいさつに添える、端末の持ち主のこと（ひとり・身近な人のときだけ。無ければ空）。
        声ではまだ確かめていないので「たぶん」とする。覚えていること（同意があり、忘れる依頼の処理中でないもの）は
        最近の分だけ、シエルとの関係は口調の下敷きとして渡す。本人の声だと分かったら、いつもどおり identify_parts が渡す"""
        k = next((k for k in self.known if k.person_id == self.owner_id), None) if self.owner_id is not None else None
        if not private or k is None:
            return ''
        about = f'[アプリを開いた人：たぶん{k.name}さん（この端末の持ち主。声ではまだ確かめていない）'
        if k.last_seen is not None:
            about += f'。前に話したのは{jst(k.last_seen)}'
        about += ']'
        if not k.notes_ok or self.store is None or not hasattr(self.store, 'memory_snapshot'):
            return about
        try:
            snapshot = await self.store.memory_snapshot(k.person_id)
        except Exception as e:
            log.warning('話者：あいさつの前に記憶を読めない error=%s', type(e).__name__)
            return about
        if snapshot is None or snapshot['blocked'] or not snapshot['consent']:
            return about
        notes = [t for _, t in snapshot['notes']][-GREETING_NOTES:]
        if notes:
            about += f'\n[{k.name}さんについて覚えていること：' + '／'.join(notes) + ']'
        return about + relationship.context(k.name, snapshot['relationship'], k.last_seen, private=True)

    @staticmethod
    def label(j: 'Judgment | None') -> str:
        """記録係・議事録の係に渡す話者の呼び名（シエルへの [発言者：…] と同じ言葉）"""
        if j is None or j.sp is None:
            return '不明'
        name = j.sp.name or j.sp.label
        return name if j.sure else 'たぶん' + name

    async def identify(self, j: 'Judgment | None', solo: bool = False, push_notes: bool = False) -> str | None:
        """発言の判定から、会話モデルに渡す 1 行（話者の行と、メモ・関係をつないだもの）を作る。None は「何も足さない」"""
        parts = await self.identify_parts(j, solo=solo, push_notes=push_notes)
        return None if parts is None else parts[0] + parts[1]

    async def identify_parts(self, j: 'Judgment | None', solo: bool = False,
                             push_notes: bool = False) -> tuple[str, str] | None:
        parts = await self._identify_parts(j, solo, push_notes)
        if self.last is not None:
            # 短い返事を比べる相手（_judge_short）。間に短い物音（「不明」）が入っても、直前に分かった人を残しておく
            self.recent, self.recent_sure, self.recent_at = self.last, self.last_sure, time.monotonic()
        self.notify()   # 人違いを分けられる人（直前の発言者）が変わる
        return parts

    async def _identify_parts(self, j: 'Judgment | None', solo: bool = False,
                              push_notes: bool = False) -> tuple[str, str] | None:
        """発言の判定（judge の結果）から、会話モデルに渡す（話者の行, メモ・関係）を作る。None は「何も足さない」。
        話者の行は「[発言者：…]」の 1 行（この会話で初めて分かったときの、前に話した日・同意のことを含む）。
        メモ・関係は、その場にいる人によって渡したり渡さなかったりするもの（無ければ空）。
        solo（ふたりきり）のとき、短くて判定できない発言は、直前の人のままとみなして何も足さない
        （「不明」を渡すと、シエルが声の判定のことを話してしまうので）。
        push_notes のとき、本人のメモを渡す（その場にいる人が、ひとり・身近な人のとき。mode.py）。
        この会話でまだ渡していなければ、途中で渡せるようになったときにも渡す。"""
        await self.refresh()
        if j is None or j.sp is None:
            if solo:
                return None
            self.last = None
            return '[発言者：不明]', ''
        e, sp, sure, score, seconds = j.e, j.sp, j.sure, j.score, j.seconds
        self.last_embedding, self.last_rows, self.last_sure = e, [], False
        self.last = sp
        self.last_short = j.short   # 短い返事で、直前の人とみなしただけ（新しい名前は付けない。_confirm_name・_name）
        k = next((k for k in self.known if k.person_id == sp.person_id), None) if sp.person_id is not None else None
        if k is None:
            # この会話で聞いた、まだ覚えていない人（判定のあとで名前を聞いた人も）
            self.last_sure = sure
            return self._session_tag(sp, sure), ''
        if not self._shared_available:
            self.last_sure = sure
            return f'[発言者：{k.name}（保存情報は現在確認できないため、以前のメモは使わない）]', ''

        # 覚えている人
        if j.owner:
            adapt, limit = OWNER_ADAPT, MAX_OWNER_ADAPT
        else:
            adapt, limit = ADAPT, MAX_ADAPT_PER_SESSION
        if (sure and score >= adapt and seconds >= 2.0 and not k.disputed
                and self._adapted < limit and self.store):
            # よく当たった声を見本に足して、マイクや部屋が変わっても当たるようにしていく。どの経路（端末）の声かの印を付ける
            # （人違いだと言われたら、split で消せるように、足した行を覚えておく）
            self._adapted += 1
            k.embeddings.append(e)
            self.last_rows = await self.store.add_voiceprints(k.person_id, [e], seconds, channel=self.channel)
        if self.store:
            await self.store.touch(k.person_id)
        self.last_sure = sure
        if not sure:
            return f'[発言者：たぶん{k.name}（声を覚えている人）]', ''
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
        return f'[発言者：{k.name}（声を覚えている人{extra}）]', memory

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
        if self.recent is sp:
            self.recent = new   # 分けた人の短い返事は、分けたあとの人と比べる
        if self.heard is not None and self.heard.sp is sp and self.heard.e is e:
            self.heard.sp = new
        if self.on_split:
            self.on_split(sp, new)
        self.notify()
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
        self._promote_pending()
        sp = self.last
        if sp is None or not self.last_sure:
            return {'status': 'pending_identity', **info, 'identity_certain': False}
        if self.last_short and entry.speaker_id != sp.speaker_id:
            # 短い発言（「田中です」）は、直前の人の声とみなしただけで、別の人が初めて名乗ったのかもしれない。
            # まだ誰にも結び付けていない名前は、短い発言の人には付けない（結び付けたあとの「いいよ」はよい）
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
        if not label:
            self._promote_pending()
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
        new_name = sp.name is None or plain_name(sp.name) != name
        if not self.last_sure or (self.last_short and new_name):
            # 短い発言で直前の人とみなしただけのときは、新しい名前を付けない（別の人が名乗ったのかもしれない）
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
        self.notify()
        if not remember:
            return {**await self.speaker_status(sp), 'status': 'session_named'}
        if self.store is None:
            return {**await self.speaker_status(sp), 'status': 'storage_unavailable'}
        if not sp.embeddings:
            return {**await self.speaker_status(sp), 'status': 'need_voice_sample'}
        try:
            pid = await self.store.remember_person(name, list(sp.embeddings), sp.person_id, channel=self.channel)
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
            self.notify()
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
        self.notify()
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
        if self.owner_id == pid:
            self.owner_id = None   # 端末の持ち主の登録も、DB では一緒に消える
        self.speakers.remove(sp)
        if self.recent is sp:
            self.recent = None
        for entry in self.name_registrations.values():
            if entry.speaker_id == sp.speaker_id:
                entry.speaker_id, entry.stage = None, 'pending_identity'
        self.last = None
        if self.heard is not None and self.heard.sp is sp:
            self.heard = None
        self.notify()
        log.info('話者：#%d の声の記録を消した', pid)
        return f'「{name}」さんの声の記録を消しました。'

    # ---- アプリの参加者パネル（名簿と最後に話した人を知らせる。この会話の間だけの直しを受ける） ----

    def state(self) -> dict:
        """アプリへ送る名簿。名前のほかは、声を覚えている人か・名前を聞いたかだけ（声の特徴や DB の番号は送らない）"""
        heard = self.heard.sp if self.heard is not None else None
        last = self.last
        owner = next((k for k in self.known if k.person_id == self.owner_id), None) if self.owner_id is not None else None
        return {
            'v': 1, 'type': 'speakers.state',
            'speakers': [{'id': s.speaker_id, 'name': s.name or s.label, 'named': s.name is not None,
                          'remembered': s.person_id is not None} for s in self.speakers],
            'speaking': heard.speaker_id if heard is not None and any(s is heard for s in self.speakers) else '',
            'speaking_sure': self.heard is not None and self.heard.sure,
            'heard': self._heard_count,   # 同じ人が続けて話しても、話すたびに光らせ直す
            # 人違いを分けられるのは、直前の発言者で、名前の分かっている人だけ（split と同じ条件）
            'correctable': last.speaker_id if last is not None and self.last_embedding is not None
            and (last.name is not None or last.person_id is not None) else '',
            # 端末の持ち主（名前と、この会話での話者）。持ち主にできるのは、直前の発言者で、確かに当てた覚えている人だけ
            'owner_name': owner.name if owner is not None else '',
            'owner': next((s.speaker_id for s in self.speakers if owner is not None and s.person_id == owner.person_id), ''),
            'pairable': last.speaker_id if last is not None and self.last_sure and last.person_id is not None
            and last.person_id != self.owner_id and self.store is not None else '',
        }

    def notify(self) -> None:
        if self.on_change is None:
            return
        now = self.state()
        if now == self._published:
            return
        self._published = now
        try:
            self.on_change(now)
        except Exception:
            log.exception('話者：名簿をアプリへ知らせられない')

    def _by_id(self, speaker_id) -> SessionSpeaker | None:
        return next((s for s in self.speakers if s.speaker_id == speaker_id), None) if isinstance(speaker_id, str) else None

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != APP_TOPIC:
            return
        try:
            msg = json.loads(packet.data.decode('utf-8'))
            if not isinstance(msg, dict):
                raise ValueError('not an object')
        except (ValueError, UnicodeDecodeError) as ex:
            log.warning('話者：アプリの直しを読めない: %s', ex)
            return
        task = asyncio.create_task(self.app_control(msg))
        self._app_tasks.add(task)
        task.add_done_callback(self._app_tasks.discard)

    async def app_control(self, msg: dict) -> str:
        """アプリの参加者パネルからの直し。名前と分けるは、この会話の間だけで、DB には書かない。
        name：名前を付ける・直す（声を覚えている人の名前は、本人が声で頼んだときだけ直せるので、ここでは直さない）。
        merge：別の人として聞いていた 2 人を、同じ人にまとめる（覚えている人にまとめたら、その声を見本に少し足す）。
        split：直前の発言を、その人から分ける。
        hello・pair・unpair：端末の持ち主を確かめる・持ち主にする・やめる（_device_control）"""
        action = msg.get('action')
        try:
            async with self._identity_lock:
                if action == 'name':
                    status = self._app_name(self._by_id(msg.get('speaker_id')), msg.get('name'))
                elif action == 'merge':
                    status = await self._app_merge(self._by_id(msg.get('speaker_id')), self._by_id(msg.get('into')))
                elif action in ('hello', 'pair', 'unpair'):
                    status = await self._device_control(action, msg)
                elif action == 'enroll_start':
                    status = self._enroll_start(msg.get('speaker_id'), msg.get('name'))
                    if status != 'enrolling' and self.on_enroll is not None:
                        # 始められなかったわけを、アプリの登録の画面に出す
                        self.on_enroll({**self.enroll_state(), 'active': False, 'status': status})
                elif action == 'enroll_cancel':
                    status = self._enroll_cancel()
                elif action == 'split':
                    sp = self._by_id(msg.get('speaker_id'))
                    if sp is None or sp is not self.last or self.state()['correctable'] != sp.speaker_id:
                        status = 'not_current_speaker'
                    else:
                        count = len(self.speakers)
                        await self.split()
                        status = 'split' if len(self.speakers) > count else 'not_split'
                else:
                    status = 'unknown_action'
        except Exception:
            log.exception('話者：アプリの直しに失敗 action=%s', action)
            status = 'failed'
        log.info('話者：アプリの直し action=%s status=%s', action, status)
        self.notify()
        return status

    def _app_name(self, sp: SessionSpeaker | None, name) -> str:
        if sp is None:
            return 'speaker_not_found'
        if sp.person_id is not None:
            return 'remembered'
        name = plain_name(name) if isinstance(name, str) else ''
        if not name or len(name) > 40:
            return 'invalid_name'
        if any(s is not sp and name in (s.name, s.label) for s in self.speakers):
            return 'name_taken'   # 同じ名前の人がいるなら、まとめる（merge）
        sp.name = name
        for entry in self.name_registrations.values():
            if entry.speaker_id == sp.speaker_id:
                entry.name = name
            elif entry.speaker_id is None and entry.name == name:
                # 声で紹介されて仮に受け付けていた名前なら、その人に結び付ける
                entry.speaker_id, entry.stage = sp.speaker_id, 'session_named'
        return 'session_named'

    async def _app_merge(self, src: SessionSpeaker | None, dst: SessionSpeaker | None) -> str:
        if src is None or dst is None or src is dst:
            return 'speaker_not_found'
        if src.person_id is not None and dst.person_id is not None:
            return 'both_remembered'
        if src.person_id is not None:
            src, dst = dst, src   # 声を覚えている人のほうを残す
        voices = list(src.embeddings)
        self._merge(src, dst)
        k = next((k for k in self.known if k.person_id == dst.person_id), None) if dst.person_id is not None else None
        if k is not None and voices and not k.disputed and self.store is not None:
            # 人がまとめたので確か。次の会話から当たるように、最近の声を少しだけ DB の見本に足す
            await self.store.add_voiceprints(k.person_id, voices[-MERGE_PRINTS:], None, channel=self.channel)
        return 'merged'

    def _merge(self, src: SessionSpeaker, dst: SessionSpeaker) -> None:
        """src を dst にまとめる（アプリでまとめたとき・人違いから回復したとき）"""
        if dst.name is None and dst.person_id is None:
            dst.name = src.name
        # まとめた声で、この会話の間は同じ人として当てる
        dst.embeddings = (dst.embeddings + src.embeddings)[-MAX_SESSION_EMBEDDINGS:]
        if dst.person_id is not None:
            k = next((k for k in self.known if k.person_id == dst.person_id), None)
            if k is not None:
                k.embeddings = k.embeddings + src.embeddings
        dst.split = dst.split or src.split
        self.speakers = [s for s in self.speakers if s is not src]
        if self.last is src:
            self.last = dst
        if self.recent is src:
            self.recent = dst
        if self.heard is not None and self.heard.sp is src:
            self.heard.sp = dst
        for entry in self.name_registrations.values():
            if entry.speaker_id == src.speaker_id:
                entry.speaker_id = dst.speaker_id
        if self.on_merge:
            self.on_merge(src, dst)

    async def _device_control(self, action: str, msg: dict) -> str:
        """端末の持ち主。端末 ID と合言葉はアプリが端末の中で作って持つ。サーバーは合言葉のハッシュだけを置く。
        hello：接続のたびに、経路の印を決め、持ち主を確かめる。pair：直前の発言者（確かに当てた覚えている人）を持ち主にする。
        unpair：持ち主をやめる（合言葉が合うときだけ）"""
        device_id, secret = msg.get('device_id'), msg.get('secret')
        if not isinstance(device_id, str) or not DEVICE_ID.match(device_id) \
                or not isinstance(secret, str) or not 16 <= len(secret) <= 256:
            if action == 'hello':
                self.device_known.set()
            return 'invalid_device'
        # 経路の印は端末 ID そのものではなく、そのハッシュの頭（DB の見本に端末 ID を残さない）
        self.channel = 'device:' + hashlib.sha256(device_id.encode()).hexdigest()[:16]
        if self.store is None:
            if action == 'hello':
                self.device_known.set()
            return 'storage_unavailable'
        secret_hash = hashlib.sha256(secret.encode()).hexdigest()
        if action == 'hello':
            pid = await self.store.device_owner(device_id, secret_hash)
            self.owner_id = pid if any(k.person_id == pid for k in self.known) else None
            log.info('話者：端末の持ち主 %s', '#%d' % self.owner_id if self.owner_id is not None else 'なし')
            self.device_known.set()
            return 'owner' if self.owner_id is not None else 'no_owner'
        if action == 'pair':
            sp = self._by_id(msg.get('speaker_id'))
            if sp is None or sp is not self.last or not self.last_sure or sp.person_id is None:
                return 'not_current_speaker'
            await self.store.pair_device(device_id, secret_hash, sp.person_id)
            self.owner_id = sp.person_id
            log.info('話者：#%d を端末の持ち主にした', sp.person_id)
            return 'paired'
        if not await self.store.unpair_device(device_id, secret_hash):
            return 'not_paired'
        self.owner_id = None
        log.info('話者：端末の持ち主をやめた')
        return 'unpaired'
