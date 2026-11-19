# -*- coding: utf-8 -*-
"""関連性で思い出す（docs/services/associative-memory-ja.md）。

記憶を、今の話題との関連度・新しさ・重要度で選び、会話の補足に「思い出したこと」として添える。
- 候補：シエルの記憶（memories：日記・ゲームの場所と出来事）と、話している本人のメモ（person_notes と note_index）。
- 関連度：埋め込みの近さと、文字の2字組の重なりの大きいほう。記憶には保存のときに使い道の鍵（keys）を足し、
  本文と一緒に埋め込む。「休もう」と「拠点」のように言葉が重ならない話題をつなぐのは、この鍵。
- 公開範囲：本人のメモは、本人と分かり、保存に同意していて、ひとり・身近な人のときだけ候補にする（eligible）。
  ゲームの記憶は今のワールドのものだけ。無効になった記憶（壊れた拠点）は「前は」として渡す。
評価器（server/benchmark/memory_recall.py）も同じ eligible・rank を使う。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import math
import os
import re
import threading
import time

import numpy as np

log = logging.getLogger('ciel-agent.recall')

TOP_K = 3                 # 1 回に添える記憶の数の上限
MIN_RELEVANCE = 0.35      # これより関係の薄い記憶は添えない（雑談に記憶を押し込まない）
RECENCY_DAYS = 30.0       # 新しさの重みが半分ほど減る目安。古くても関係が深ければ思い出せるよう、下限を残す
RECENCY_FLOOR = 0.6
KEY_CHARS = 120
DEFAULT_EMBEDDER = 'cl-nagoya/ruri-v3-30m'
DEFAULT_EMBEDDER_REVISION = '24899e5de370b56d179604a007c0d727bf144504'   # イメージに入れる版（Dockerfile と同じ）
EMBED_MODEL = os.environ.get('CIEL_RECALL_EMBEDDER', DEFAULT_EMBEDDER).strip()
# ruri-v3 の埋め込みは、関係のない文どうしでも近さが 0.6 前後になる。それより上を 0〜1 に引き直す
COSINE_FLOOR = float(os.environ.get('CIEL_RECALL_COSINE_FLOOR', '0.65'))

PRIVATE = ('solo', 'close')


@dataclass
class Candidate:
    """思い出す候補の 1 件。id は 'mem:12'（シエルの記憶）・'note:5'（人のメモ）"""
    id: str
    kind: str                         # diary / game_place / game_event / note
    text: str
    at: datetime
    keys: str = ''
    importance: int = 3
    person_id: int | None = None      # note のときの本人
    world: str | None = None          # ゲームの記憶のワールド
    ref: str | None = None            # ゲーム側の正本への参照
    invalidated_at: datetime | None = None
    embedding: np.ndarray | None = None


@dataclass
class Situation:
    """今回の発言の場。person_id は、声で本人と分かり、メモの保存に同意していて、忘れる依頼の処理中でない人だけ"""
    presence: str = 'solo'
    person_id: int | None = None
    world: str | None = None


@dataclass
class Recalled:
    id: str
    kind: str
    text: str
    at: datetime
    score: float
    relevance: float
    past: bool = False
    ref: str | None = None
    details: dict = field(default_factory=dict)


def eligible(c: Candidate, s: Situation) -> bool:
    """この場で思い出してよい記憶か（公開範囲・本人・ワールド）。評価器も同じ判定を使う"""
    if c.kind == 'note':
        return s.presence in PRIVATE and s.person_id is not None and c.person_id == s.person_id
    if c.kind in ('game_place', 'game_event') and c.world is not None:
        return c.world == s.world
    return True


# 文字の重なりで比べる単位：漢字 1 字、カタカナ・英数字の 2 字組。ひらがなは活用や助詞で形が変わるので使わない
# （「休もう」と「休む」は 2 字組では重ならないが、漢字の「休」で重なる）。どの話にも出る漢字は外す
_KANJI = re.compile(r'[一-鿿㐀-䶿々]')
_RUNS = re.compile(r'[゠-ヿー]+|[A-Za-z0-9]+')
COMMON_KANJI = set('今日前後年月時人方事物何私僕分中上下大小見行来言思同')


def units(text: str) -> set[str]:
    text = text or ''
    out = {k for k in _KANJI.findall(text) if k not in COMMON_KANJI}
    for run in _RUNS.findall(text):
        run = run.lower()
        out |= {run[i:i + 2] for i in range(len(run) - 1)} if len(run) > 1 else {run}
    return out


def lexical(query: str, doc: str) -> float:
    """問いの単位のうち、記憶（本文と鍵）にもある割合"""
    q = units(query)
    return len(q & units(doc)) / len(q) if q else 0.0


# 時間で範囲を決める問い（「きのう何したっけ」）。その日の記憶を、言葉が重ならなくても関係があるとみなす
TIME_MATCH = 0.6
_DAYS_AGO = re.compile(r'([0-9０-９一二三四五六七八九十]+)\s*日前')
_KANJI_NUM = {c: i for i, c in enumerate('〇一二三四五六七八九', 0)}


def _number(text: str) -> int | None:
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
    if text.isdigit():
        return int(text)
    if text == '十':
        return 10
    if '十' in text:
        tens, _, ones = text.partition('十')
        return (_KANJI_NUM.get(tens, 1) if tens else 1) * 10 + (_KANJI_NUM.get(ones, 0) if ones else 0)
    return _KANJI_NUM.get(text)


def time_window(query: str, now: datetime) -> tuple[datetime, datetime] | None:
    """問いが指す日の範囲（日本時間の 0 時から）。指していなければ None"""
    days = None
    if 'おととい' in query or '一昨日' in query:
        days = (2, 2)
    elif 'きのう' in query or '昨日' in query or '昨晩' in query or 'ゆうべ' in query:
        days = (1, 1)
    elif '先週' in query:
        days = (13, 7)
    elif '今朝' in query:
        days = (0, 0)
    else:
        m = _DAYS_AGO.search(query)
        n = _number(m.group(1)) if m else None
        if n is not None:
            days = (n, n)
    if days is None:
        return None
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    return midnight - timedelta(days=days[0]), midnight - timedelta(days=days[1] - 1)


def cosine_relevance(q: np.ndarray | None, d: np.ndarray | None) -> float:
    if q is None or d is None:
        return 0.0
    denom = float(np.linalg.norm(q) * np.linalg.norm(d))
    if denom == 0:
        return 0.0
    cos = float(np.dot(q, d)) / denom
    return max(0.0, min(1.0, (cos - COSINE_FLOOR) / (1 - COSINE_FLOOR)))


def recency(at: datetime, now: datetime) -> float:
    days = max(0.0, (now - at).total_seconds() / 86400)
    return RECENCY_FLOOR + (1 - RECENCY_FLOOR) * math.exp(-days / RECENCY_DAYS)


def weight(importance: int) -> float:
    return 0.7 + 0.075 * max(1, min(5, importance))


def document(c: Candidate) -> str:
    """埋め込み・文字の重なりで比べる文（本文と鍵）"""
    return c.text + (f'\n{c.keys}' if c.keys else '')


def rank(candidates: list[Candidate], s: Situation, query: str, query_vec: np.ndarray | None, now: datetime,
         *, k: int | None = None, min_relevance: float | None = None) -> list[Recalled]:
    k = TOP_K if k is None else k
    min_relevance = MIN_RELEVANCE if min_relevance is None else min_relevance
    out = []
    window = time_window(query, now)
    for c in candidates:
        if not eligible(c, s):
            continue
        sem = cosine_relevance(query_vec, c.embedding)
        lex = lexical(query, document(c))
        when = TIME_MATCH if window is not None and window[0] <= c.at < window[1] else 0.0
        rel = max(sem, lex, when)
        if rel < min_relevance:
            continue
        past = c.invalidated_at is not None and c.invalidated_at <= now
        out.append(Recalled(id=c.id, kind=c.kind, text=c.text, at=c.at, ref=c.ref, past=past,
                            relevance=round(rel, 4), score=round(rel * recency(c.at, now) * weight(c.importance), 4),
                            details={'semantic': round(sem, 4), 'lexical': round(lex, 4), 'time': when}))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:k]


def ago(at: datetime, now: datetime) -> str:
    days = (now.date() - at.astimezone(now.tzinfo).date()).days if now.tzinfo else (now - at).days
    if (now - at).total_seconds() < 3600:
        return 'さっき'
    if days <= 0:
        return '今日'
    if days == 1:
        return 'きのう'
    if days < 30:
        return f'{days}日前'
    return f'{days // 30}か月ほど前' if days < 365 else 'ずっと前'


def context(items: list[Recalled], now: datetime, header: str) -> str:
    """会話へ添える補足。見出しは prompts/recall_note.md（中身の名前だけ。使い方は固定の指示 prompts/mind.md に書く。ciel-prompt-writing）"""
    if not items:
        return ''
    lines = [header.strip()]
    for r in items:
        when = ago(r.at, now)
        # かっこ書きにしない（返事に注釈を書き出させやすい。2026-11-20 の比較）
        text = f'{r.text}。でも、その場所は今はもう無い' if r.past else r.text
        lines.append(f'- {when}：{text}')
    return '\n'.join(lines)


# ---- 埋め込み ----

class Embedder:
    """文を埋め込む。重い計算はスレッドで行い、会話のイベントループを止めない"""
    name = ''

    def embed(self, texts: list[str], *, query: bool) -> np.ndarray:
        raise NotImplementedError

    async def aembed(self, texts: list[str], *, query: bool) -> np.ndarray:
        return await asyncio.to_thread(self.embed, texts, query=query)

    async def warm(self) -> None:
        """会話の始めに裏で読み込む（失敗しても会話は続ける。思い出すときに読み直す）"""
        try:
            await self.aembed(['準備'], query=True)
        except Exception as e:
            log.warning('思い出し：埋め込みモデルを読み込めない：%s', type(e).__name__)


class SentenceEmbedder(Embedder):
    """sentence-transformers のモデル（既定は ruri-v3-30m。CPU）。初めて使うときに読み込む"""

    def __init__(self, name: str, revision: str | None = None) -> None:
        self.name, self.revision = name, revision
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            return self._load_locked()

    def _load_locked(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer   # 重いので使うときに読む
            t0 = time.perf_counter()
            self._model = SentenceTransformer(self.name, device='cpu', revision=self.revision)
            log.info('思い出し：埋め込みモデル %s を読み込んだ（%.1f 秒）', self.name, time.perf_counter() - t0)
        return self._model

    def embed(self, texts: list[str], *, query: bool) -> np.ndarray:
        prefix = '検索クエリ: ' if query else '検索文書: '
        vectors = self._load().encode([prefix + t for t in texts], normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype=np.float32)


def make_embedder() -> Embedder | None:
    """CIEL_RECALL_EMBEDDER が空なら埋め込みを使わない（文字の重なりだけで思い出す）"""
    if not EMBED_MODEL:
        return None
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        log.warning('思い出し：sentence-transformers が無いので、文字の重なりだけで思い出す')
        return None
    return SentenceEmbedder(EMBED_MODEL, DEFAULT_EMBEDDER_REVISION if EMBED_MODEL == DEFAULT_EMBEDDER else None)


# ---- 使い道の鍵 ----

class KeyWriter:
    """記憶に、思い出すきっかけになる言葉（使い道・言い換え・関係する話題）を付ける。まとめて 1 回の推論で書く"""
    BATCH = 12

    def __init__(self, instructions: str, client=None, model: str = '') -> None:
        self.instructions = instructions
        self.client = client
        self.model = model

    async def write(self, items: list[tuple[str, str]]) -> dict[str, str]:
        """[(id, 本文)] → {id: 鍵}。書けなかった分は含めない"""
        import models
        if self.client is None:
            self.client = models.create_client('notes')   # メモの記録係と同じ文字のモデル（growth.py と同じ作り方）
        request = {'memories': [{'id': i, 'text': t} for i, t in items]}
        r = await models.client_for('notes', self.client).chat.completions.create(**models.options(
            'notes', model=self.model or os.environ.get('CIEL_NOTES_MODEL', 'gpt-5.4-mini'), reasoning_effort='low',
            response_format={'type': 'json_object'},
            messages=[{'role': 'system', 'content': self.instructions},
                      {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}]))
        models.record('notes', models.LOCAL_MODEL if models.is_local('notes') else self.model or 'notes', getattr(r, 'usage', None))
        result = json.loads(r.choices[0].message.content or '{}').get('keys') or {}
        wanted = {i for i, _ in items}
        return {str(i): ' '.join(str(k).split())[:KEY_CHARS] for i, k in result.items()
                if str(i) in wanted and isinstance(k, str) and k.strip()}


class Indexer:
    """鍵と埋め込みがまだ無い記憶・メモを、会話の裏で少しずつ埋める（memory_jobs の index_memories）。
    本文が変わったメモは埋め込み直す（note_index.embedded_text と比べる）"""
    POLL = 30.0

    def __init__(self, store, embedder: Embedder | None, keys: KeyWriter | None) -> None:
        self.store, self.embedder, self.keys = store, embedder, keys
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def poke(self) -> None:
        self._wake.set()

    def start(self) -> None:
        if self._task is None and self.store is not None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        from memory_jobs import run_memory_job
        while True:
            try:
                while await run_memory_job('index_memories', self.step):
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info('思い出し：記憶の索引を作れない：%s', type(e).__name__)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), self.POLL)
            except asyncio.TimeoutError:
                pass

    async def step(self) -> bool:
        """1 回分を進める。まだ残っていれば True"""
        model = self.embedder.name if self.embedder is not None else ''
        rows = await self.store.unindexed(model, self.keys is not None, KeyWriter.BATCH)
        if not rows:
            return False
        need_keys = [(r['id'], r['text']) for r in rows if r['keys'] is None]
        keys = {}
        if need_keys and self.keys is not None:
            try:
                keys = await self.keys.write(need_keys)
            except Exception as e:
                log.info('思い出し：鍵を書けない：%s', type(e).__name__)
                keys = {}
        docs, done = [], []
        for r in rows:
            k = keys.get(r['id'], r['keys'] if r['keys'] is not None else ('' if self.keys is None else None))
            if k is None:
                continue   # 鍵は次の機会に書く（本文だけで埋め込むと、鍵を書いたあとで埋め込み直しになる）
            done.append((r, k))
            docs.append(r['text'] + (f'\n{k}' if k else ''))
        if not done:
            return False
        vectors = await self.embedder.aembed(docs, query=False) if self.embedder is not None else [None] * len(done)
        for (r, k), doc, v in zip(done, docs, vectors):
            await self.store.set_index(r['id'], r['text'], k, v, model, doc)
        return len(rows) == KeyWriter.BATCH


class Recall:
    """会話の 1 ターンに、思い出したことを選ぶ"""

    # 同じ記憶を続けて添えると、同じ話を繰り返しやすい。この時間のうちに添えた記憶は、点を下げる
    REPEAT_SECONDS = 300.0
    REPEAT_FACTOR = 0.5

    def __init__(self, store, embedder: Embedder | None, *, clock=None, monotonic=time.monotonic) -> None:
        self.store, self.embedder = store, embedder
        self.clock = clock
        self.monotonic = monotonic
        self.last: list[Recalled] = []
        self._shown: dict[str, float] = {}

    async def for_turn(self, query: str, s: Situation) -> list[Recalled]:
        query = ' '.join((query or '').split())
        if not query or self.store is None:
            self.last = []
            return []
        from jst import JST
        now = self.clock() if self.clock else datetime.now(JST)
        t0 = time.perf_counter()
        model = self.embedder.name if self.embedder is not None else ''
        candidates = await self.store.recall_candidates(model, s.world, s.person_id if s.presence in PRIVATE else None)
        qv = (await self.embedder.aembed([query], query=True))[0] if self.embedder is not None else None
        t = self.monotonic()
        recent = {i for i, at in self._shown.items() if t - at < self.REPEAT_SECONDS}
        items = rank(candidates, s, query, qv, now, k=len(candidates) or TOP_K)
        for r in items:
            if r.id in recent:
                r.score = round(r.score * self.REPEAT_FACTOR, 4)
        items = sorted(items, key=lambda r: r.score, reverse=True)[:TOP_K]
        for r in items:
            self._shown[r.id] = t
        if items:
            await self.store.mark_recalled([r.id for r in items])
        self.last = items
        import debug_log
        debug_log.record('recall', candidates=len(candidates), chosen=[r.id for r in items],
                         scores=[r.score for r in items], ms=round((time.perf_counter() - t0) * 1000, 1))
        return items
