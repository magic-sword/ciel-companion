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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from livekit import rtc

log = logging.getLogger('ciel-agent.speakers')

SR = 16000
BUFFER_SECONDS = 30          # 発言の声を取り出すために、届いた声をためておく長さ
LEAD_SECONDS = 0.8           # 「話し始めた」の知らせは実際より遅れて届くので、少し前から取る
MAX_SECONDS = 8.0            # 長い発言は最後の 8 秒だけ使う（計算を軽くする）
MIN_VOICED = float(os.environ.get('CIEL_SPK_MIN_SECONDS', '1.0'))   # これより短い発言は「不明」
# コサイン類似度の基準（Zoom を通した声で測って決める。docs/decisions/speaker-identification-ja.md）
MATCH = float(os.environ.get('CIEL_SPK_MATCH', '0.45'))   # これ以上なら同じ人
MAYBE = float(os.environ.get('CIEL_SPK_MAYBE', '0.35'))   # これ以上なら「たぶん」
ADAPT = float(os.environ.get('CIEL_SPK_ADAPT', '0.60'))   # これ以上なら、覚えている人の見本に足す
MAX_SESSION_EMBEDDINGS = 20
MAX_ADAPT_PER_SESSION = 3
SPLIT_BONUS = 0.05          # 人違いだと言われて分けた人を、元の人より少し優先する
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
    t = t.astimezone(timezone(timedelta(hours=9)))
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
    split: bool = False              # 人違いだと言われて、ほかの人から分けた人

    def add(self, e: np.ndarray) -> None:
        self.embeddings.append(e)
        del self.embeddings[:-MAX_SESSION_EMBEDDINGS]


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
        self._unknown_count = 0
        self._adapted = 0
        self.last_embedding: np.ndarray | None = None   # 直前の発言の声の特徴（人違いを直すとき使う）
        self.last_sure = False                           # 直前の発言者を、自信を持って判定したか（メモを読むときに使う）
        self._note_ids: list[int] = []                   # 直前に読んだメモの番号 → DB の行（忘れるときに使う）
        self._note_owner: int | None = None
        self.last_rows: list[int] = []                   # 直前の発言で DB に足した見本の行

    async def load(self) -> None:
        if self.store is not None:
            self.known = [Known(pid, name, embs, seen, disputed=False, notes_ok=ok, note_count=n)
                          for pid, name, embs, seen, ok, n in await self.store.load_all()]
        log.info('覚えている人：%d 人', len(self.known))

    def _new_unknown_label(self) -> str:
        i = self._unknown_count
        self._unknown_count += 1
        letters = string.ascii_uppercase
        return '知らない人' + (letters[i] if i < 26 else str(i + 1))

    async def identify(self, e: np.ndarray | None, seconds: float, solo: bool = False) -> str | None:
        """発言の声の特徴から、会話モデルに渡す 1 行を作る。None は「何も足さない」。
        solo（2 人）のとき、短くて判定できない発言は、直前の人のままとみなして何も足さない
        （「不明」を渡すと、シエルが声の判定のことを話してしまうので）。"""
        if e is None or seconds < MIN_VOICED:
            log.info('話者：%s（声 %.1f 秒）', '短い発言（直前の人のまま）' if solo else '不明', seconds)
            if solo:
                return None
            self.last = None
            return '[発言者：不明]'

        self.last_embedding, self.last_rows, self.last_sure = e, [], False
        # 覚えている人と、この会話で聞いた（まだ覚えていない）人を、まとめて比べて一番近い人にする。
        # 人違いだと言われて分けた人（split）は、声が似ているので、元の人より少し優先する
        known = sorted(((best_score(e, k.embeddings), k) for k in self.known), key=lambda x: -x[0])
        session = sorted(((best_score(e, s.embeddings) + (SPLIT_BONUS if s.split else 0.0), s)
                          for s in self.speakers if s.person_id is None), key=lambda x: -x[0])
        k_score, k = known[0] if known else (-1.0, None)
        s_score, s = session[0] if session else (-1.0, None)

        # 1. この会話で聞いた、まだ覚えていない人
        if s is not None and s_score >= MATCH and s_score >= k_score:
            s.add(e)
            self.last = s
            log.info('話者：この会話の %s（%.2f）', '名前を聞いた人' if s.name else s.label, s_score)
            return self._session_tag(s)

        # 2. 覚えている人
        if k is not None and k_score >= MAYBE:
            score = k_score
            sp = next((s for s in self.speakers if s.person_id == k.person_id), None)
            if sp is None:
                sp = SessionSpeaker(label=k.name, person_id=k.person_id, name=k.name)
                self.speakers.append(sp)
            sp.add(e)
            self.last = sp
            # 似た声の人（2 番目に近い人）との差が小さいときも、断定しない
            runner_up = max(known[1][0] if len(known) > 1 else -1.0, s_score)
            sure = score >= MATCH and score - runner_up >= MARGIN
            log.info('話者：覚えている人 #%d（%.2f、次点との差 %.2f%s）', k.person_id, score, score - runner_up,
                     '' if sure else '、たぶん')
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
            extra = ''
            if not sp.announced:
                # この会話で初めて分かったときだけ、前に話した日と、メモのことを添える（本人が話しているときだけ）
                sp.announced = True
                if k.last_seen is not None:
                    extra += f'。前に話したのは{jst(k.last_seen)}'
                if not k.notes_ok:
                    extra += '。お話を覚える同意はまだ'
                elif k.note_count:
                    extra += '。この人について覚えていることがある'
            return f'[発言者：{k.name}（声を覚えている人{extra}）]'

        # 3. 初めての人
        sp = SessionSpeaker(label=self._new_unknown_label())
        sp.add(e)
        self.speakers.append(sp)
        self.last = sp
        log.info('話者：初めての声 → %s（一番近い %.2f）', sp.label, max(k_score, s_score))
        return self._session_tag(sp)

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
        log.info('話者：人違いを直した（%s から分けた）', '覚えている人 #%d' % sp.person_id if sp.person_id else 'この会話の人')
        if new_name:
            return (f'わかりました。直前の発言は{old}さんではなく、{new_name}さんとして区別します'
                    '（この会話の間。声はまだ保存していません）。声を覚えてよいか聞いてください。')
        return f'わかりました。直前の発言は{old}さんではない、別の方として区別します（呼び名：{new.label}）。お名前を聞いてください。'

    @staticmethod
    def _session_tag(sp: 'SessionSpeaker') -> str:
        """まだ声を覚えていない人。名前を聞いたかどうかも伝える（覚えている人と区別できるように）"""
        if sp.name:
            return f'[発言者：{sp.name}（名前はこの会話の間だけ。声は覚えていない）]'
        return f'[発言者：{sp.label}（まだ名前を知らない人）]'

    def find(self, label: str) -> SessionSpeaker | None:
        label = label.strip().strip('[]').replace('発言者：', '').removeprefix('たぶん').split('（')[0]
        label = plain_name(label)
        for s in self.speakers:
            if label in (s.label, s.name):
                return s
        return None

    async def name(self, label: str, name: str, remember: bool) -> str:
        sp = self.find(label)
        if sp is None:
            return f'「{label}」という発言者は、この会話にいません。[発言者：…] に出た呼び名を使ってください。'
        name = plain_name(name)
        if sp.person_id is not None:
            # もう覚えている人。同意を聞き直さない（呼び名を直すのは rename）
            return (f'{sp.name}さんの声は、もう覚えています（同意も前にもらっています）。覚え直す必要はありません。'
                    '呼び名を直したいと言われたときは rename_speaker を使ってください。')
        sp.name = sp.label = name
        if not remember:
            return f'この会話の間だけ「{name}」と呼びます（声は保存していません）。'
        if self.store is None:
            return f'「{name}」と呼びます。ただ、記録の場所が使えないので、声はこの会話の間だけ覚えています。'
        if sp.person_id is None:
            sp.person_id = await self.store.add_person(name)
            self.known.append(Known(sp.person_id, name, []))
        else:
            await self.store.rename(sp.person_id, name)
        k = next(k for k in self.known if k.person_id == sp.person_id)
        k.name = name
        new = [e for e in sp.embeddings if not any(e is x for x in k.embeddings)]
        k.embeddings.extend(new)
        await self.store.add_voiceprints(sp.person_id, new, None)
        # 覚えてよいかの質問は「お名前と声、それからお話も少し」なので、メモを残す同意も一緒にもらっている
        await self.store.set_notes_consent(sp.person_id)
        k.notes_ok = True
        if self.last is sp:
            self.last_sure = True   # 本人が同意したので、この会話ではメモを読み書きしてよい
        log.info('話者：#%d として声を覚えた（見本 %d）', sp.person_id, len(new))
        return f'「{name}」さんのお名前と声を覚えました。次の会話でも分かります。お話も少しずつ覚えていきます。'

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
        log.info('話者：#%d がお話を覚えることに同意した', k.person_id)
        return f'{k.name}さんのお話を、少しずつ覚えていきます。'

    async def recall(self) -> str:
        k = self.current_person()
        if k is None or self.store is None:
            return 'いま話している方が誰か確かではないので、覚えていることは読めません。'
        if not k.notes_ok:
            return f'{k.name}さんからは、お話を覚える同意をまだもらっていません。'
        rows = await self.store.notes(k.person_id)
        self._note_ids, self._note_owner = [i for i, _ in rows], k.person_id
        if not rows:
            return f'{k.name}さんについて、まだ覚えていることはありません。'
        return f'{k.name}さんについて覚えていること：\n' + '\n'.join(f'{n}. {t}' for n, (_, t) in enumerate(rows, 1))

    async def forget_notes(self, numbers: list[int]) -> str:
        k = self.current_person()
        if k is None or self.store is None or self._note_owner != k.person_id:
            return '先に recall_about_speaker で、いま話している方のメモを読んでください。'
        ids = [self._note_ids[n - 1] for n in numbers if 1 <= n <= len(self._note_ids)]
        if not ids:
            return 'その番号のメモはありません。'
        await self.store.change_notes(k.person_id, [], {}, ids)
        k.note_count = await self.store.count_notes(k.person_id)
        self._note_ids, self._note_owner = [], None
        log.info('話者：#%d のメモを %d 件消した', k.person_id, len(ids))
        return f'{len(ids)} 件、忘れました。'

    async def rename(self, new_name: str) -> str:
        """呼び名を直す（聞き間違えたとき、呼び方を変えてほしいとき）。直せるのは、いま話している本人の呼び名だけ"""
        sp = self.last
        if sp is None:
            return '呼び名を直せるのは、ご本人が話しているときだけです。直したい方ご本人に、もう一度言ってもらってください。'
        if sp.name is None:
            return 'まだお名前を聞いていない方です。name_speaker で名前を付けてください。'
        old, new = sp.name, plain_name(new_name)
        if not new or new == old:
            return f'呼び名は「{old}」のままです。'
        sp.name = sp.label = new
        if sp.person_id is None:
            return f'呼び名を「{old}」から「{new}」に直しました（この会話の間だけ。声は保存していません）。'
        if self.store is not None:
            await self.store.rename(sp.person_id, new)
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
        parts = [s.label + ('（声を覚えている人）' if s.person_id is not None else '') for s in self.speakers]
        return 'この会話で声を聞いた人：' + '、'.join(parts)

    async def forget(self, name: str) -> str:
        """本人の依頼のときだけ：直前の発言者が、その名前の覚えている人であること"""
        sp = self.last
        if sp is None or sp.person_id is None or plain_name(name) not in (sp.name, sp.label):
            return 'ご本人からの依頼のときだけ消せます。消したい方ご本人に、もう一度お願いしてもらってください。'
        pid = sp.person_id
        if self.store is not None:
            await self.store.delete_person(pid)
        self.known = [k for k in self.known if k.person_id != pid]
        self.speakers.remove(sp)
        self.last = None
        log.info('話者：#%d の声の記録を消した', pid)
        return f'「{name}」さんの声の記録を消しました。'
