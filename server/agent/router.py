# -*- coding: utf-8 -*-
"""遊んでいるあいだ、相手の発言を心へ回すかを、例文との意味の近さで見分ける係（小脳と心の振り分けの 2 段目）。
docs/conversation-pipeline-ja.md の 3 章、docs/decisions/semantic-route-ja.md。

- 1 段目は今までどおり決まった言葉（mind.py の GAME_ASK など）。そこで小脳に決まった発言だけを、ここで見直す。
- 例文：道具ごとの「呼ぶきっかけ」（ゲームの道具の _meta の ciel/triggers と、ゲームの決まりの goal_triggers・
  talker_examples。game_env.py の seeds。スキルのトリガーと同じ考え方で、道具の横にどんな頼みで呼ぶかを書いておく）と、小脳でよい発言（talker）、遊びながら育った例文（DB の route_examples。実際に
  呼んだ道具の名前つき）。発言と例文をベクトルにして、いちばん近いきっかけの例文が THRESHOLD 以上で、
  いちばん近い小脳の例文より MARGIN 以上近ければ、心へ回す。名前（シエル）と記号は外して比べる（「おはよう、シエル」に
  引っぱられ、「シエルどこにいる？」が小脳へ回った。2026-11-07）。
- 育ち方（learn）：
  - 心が体・ゲームの道具を呼んだ発言 → 心の例文（tool）
  - 小脳が「渡しますね」と約束だけして、あとで心がその約束を道具でやった発言 → 心の例文（promise。取りこぼしの受け皿）
  - ここで心へ回したのに、心が道具を使わなかった発言 → 小脳の例文（no_tool。回しすぎを直す）
  ほとんど同じ例文がすでにあれば足さない。逆の印のほとんど同じ例文があれば、新しいほうに置き換える。
  持ち主の発言だけ・60 字まで。ゲームごとに LEARNED_MAX 個まで、古いものから消す。
- 速さ：ベクトル化 1 回 0.1 秒ほど（OpenAI text-embedding-3-small、256 次元）。ROUTE_TIMEOUT を過ぎたら小脳のまま
  （取りこぼしは約束の受け皿が拾う）。料金は 1 回 0.00001 ドル以下。
"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

import numpy as np
import openai

import debug_log

log = logging.getLogger('ciel-agent.router')

MODEL = os.environ.get('CIEL_ROUTE_EMBED_MODEL', 'text-embedding-3-small')
DIMS = 256
THRESHOLD = float(os.environ.get('CIEL_ROUTE_THRESHOLD', '0.5'))   # 記録 172 発言で測って決めた（決め方は決定記録）
MARGIN = 0.05
ROUTE_TIMEOUT = 0.6
LEARN_CHARS = 60
# 育てる例文の長さ（名前と記号を外して）。短い返事（「うん、お願い」）は前の流れしだいで意味が変わり、長い発言は
# いくつもの話がまざる。どちらも、それだけで心へ回すかを決める例文にならない（「うん、お願い」が渡すきっかけになった。2026-11-07）
LEARN_MIN = 7
LEARN_MAX = 30
SAME = 0.97          # これ以上近ければ、同じ例文とみなす
LEARNED_MAX = 500
SEEDS_DIR = Path(__file__).parent / 'config' / 'routes'
NAME = re.compile(r'シエル|しえる|シール|CL|ciel', re.I)
PUNCT = re.compile(r'[\s、。，．,.!?！？…〜ー「」]+')


def norm(text: str) -> str:
    """比べる形：名前と記号を外す"""
    return PUNCT.sub(' ', NAME.sub('', text)).strip() or text.strip()


def seeds(game: str) -> list[tuple[str, str | None]]:
    """最初の例文：(文, 道具の名前)。小脳でよい発言は道具の名前が None"""
    path = SEEDS_DIR / f'{game}.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    out = [(t, tool) for tool, texts in (data.get('tools') or {}).items() for t in texts]
    return out + [(t, None) for t in data.get('talker') or []]


class Router:
    def __init__(self, game: str, *, store=None, client=None, seeds=None) -> None:
        self.game = game
        self._seeds = seeds         # 最初の例文（無ければ config/routes/<game>.json）
        self.store = store          # speaker_store.Store（育った例文。無ければ最初の例文だけ）
        self._client = client
        self._texts: list[str] = []
        self._tools: list[str | None] = []          # その例文で呼ぶ道具（小脳でよい発言は None）
        self._labels = np.zeros(0, dtype=np.int8)   # 1：心へ・0：小脳
        self._vecs = np.zeros((0, DIMS), dtype=np.float32)
        self._ready: asyncio.Task | None = None

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    async def _embed(self, texts: list[str]) -> np.ndarray:
        r = await self.client.embeddings.create(model=MODEL, input=[norm(t) for t in texts], dimensions=DIMS)
        v = np.array([d.embedding for d in r.data], dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def start(self) -> None:
        """例文を読み込み始める（会話の始め。待たない）"""
        if self._ready is None:
            self._ready = asyncio.create_task(self._load())

    async def _load(self) -> None:
        s = list(self._seeds) if self._seeds is not None else seeds(self.game)
        texts, tools = [t for t, _ in s], [tool for _, tool in s]
        vecs = await self._embed(texts) if texts else np.zeros((0, DIMS), dtype=np.float32)
        if self.store is not None:
            try:
                rows = await self.store.route_examples(self.game)
            except Exception as e:
                log.warning('振り分け：育った例文を読めない（最初の例文だけで見る）: %s', type(e).__name__)
                rows = []
            if rows:
                texts += [t for t, _, _ in rows]
                tools += [tool for _, tool, _ in rows]
                learned = np.array([v for _, _, v in rows], dtype=np.float32)
                vecs = np.vstack([vecs, learned])
        self._texts, self._tools, self._vecs = texts, tools, vecs
        self._labels = np.array([int(t is not None) for t in tools], dtype=np.int8)
        log.info('振り分け：例文 %d 個（心へ %d・小脳 %d）', len(texts), int(self._labels.sum()), int((self._labels == 0).sum()))

    def _scores(self, v: np.ndarray) -> tuple[float, float, int, int]:
        sims = self._vecs @ v
        pos, neg = np.where(self._labels == 1)[0], np.where(self._labels == 0)[0]
        ip = int(pos[np.argmax(sims[pos])]) if len(pos) else -1
        ineg = int(neg[np.argmax(sims[neg])]) if len(neg) else -1
        return (float(sims[ip]) if ip >= 0 else 0.0, float(sims[ineg]) if ineg >= 0 else 0.0, ip, ineg)

    async def wants_mind(self, text: str) -> str | None:
        """この発言を心へ回すなら、いちばん近いきっかけの道具の名前。回さない・読み込み中・時間切れ・失敗なら None"""
        if not text.strip():
            return None
        try:
            self.start()
            await asyncio.wait_for(asyncio.shield(self._ready), ROUTE_TIMEOUT)
            v = (await asyncio.wait_for(self._embed([text]), ROUTE_TIMEOUT))[0]
        except Exception as e:   # 時間切れ・つながらない：小脳のまま（約束の受け皿が拾う）
            log.warning('振り分け：意味で見られない（小脳のまま）: %s', type(e).__name__)
            return None
        if not len(self._vecs):
            return None
        sp, sn, ip, ineg = self._scores(v)
        ok = sp >= THRESHOLD and sp - sn >= MARGIN
        debug_log.record('route_semantic', text=text[:LEARN_CHARS], mind=round(sp, 3), talker=round(sn, 3), to_mind=ok,
                         tool=self._tools[ip] if ip >= 0 else None,
                         near_mind=self._texts[ip] if ip >= 0 else None, near_talker=self._texts[ineg] if ineg >= 0 else None)
        return self._tools[ip] if ok else None

    async def learn(self, text: str, tool: str | None, source: str) -> str:
        """遊びながら例文を育てる。何をしたかを返す（added・same・replaced・skip）"""
        text = text.strip()
        if not LEARN_MIN <= len(norm(text).replace(' ', '')) <= LEARN_MAX:
            return 'skip'
        text = text[:LEARN_CHARS]
        try:
            if self._ready is not None:
                await self._ready
            v = (await self._embed([text]))[0]
        except Exception as e:
            log.warning('振り分け：例文を育てられない: %s', type(e).__name__)
            return 'skip'
        to_mind = tool is not None
        label = 1 if to_mind else 0
        what = 'added'
        if len(self._vecs):
            sims = self._vecs @ v
            same = np.where(sims >= SAME)[0]
            if any(self._labels[i] == label for i in same):
                return 'same'
            if len(same):   # 逆の印のほとんど同じ例文：新しいほうに置き換える
                keep = np.ones(len(self._texts), dtype=bool)
                keep[same] = False
                for i in same:
                    if self.store is not None:
                        await self._forget(self._texts[i])
                self._texts = [t for t, k in zip(self._texts, keep) if k]
                self._tools = [t for t, k in zip(self._tools, keep) if k]
                self._labels, self._vecs = self._labels[keep], self._vecs[keep]
                what = 'replaced'
        self._texts.append(text)
        self._tools.append(tool)
        self._labels = np.append(self._labels, np.int8(label))
        self._vecs = np.vstack([self._vecs, v[None, :]])
        if self.store is not None:
            try:
                await self.store.add_route_example(self.game, tool, text, v, source, LEARNED_MAX)
            except Exception as e:
                log.warning('振り分け：例文を残せない: %s', type(e).__name__)
        log.info('振り分け：例文を%s（%s、%s）', {'added': '足した', 'replaced': '置き換えた'}[what], tool or '小脳', source)
        debug_log.record('route_learn', text=text, tool=tool, source=source, what=what)
        return what

    async def _forget(self, text: str) -> None:
        try:
            await self.store.remove_route_example(self.game, text)
        except Exception as e:
            log.warning('振り分け：例文を消せない: %s', type(e).__name__)
