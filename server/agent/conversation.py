"""接続中だけの共通会話履歴。音声・本文をファイルや DB には保存しない。"""
import asyncio
from dataclasses import dataclass, field
import re
import time
import unicodedata
from research import ResearchBook


@dataclass
class Turn:
    id: int
    at: float
    role: str
    text: str = ''
    speaker: object | None = None
    label: str = '不明'
    sure: bool = False
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    clipped: bool = False
    source_id: str | None = None

    @property
    def owner(self):
        return self.speaker if self.sure else None

    @property
    def name(self) -> str:
        if self.role == 'assistant':
            return 'シエル'
        if self.speaker is None:
            return self.label
        name = self.speaker.name or self.speaker.label
        return name if self.sure else f'たぶん{name}'


class Conversation:
    def __init__(self, max_turns: int = 3000, max_chars: int = 2_000_000):
        self.turns: list[Turn] = []
        self.max_turns, self.max_chars = max_turns, max_chars
        self.last_id = 0
        self.dropped_through = 0
        self._chars = 0
        self.research = ResearchBook()

    def reserve(self, at: float | None = None, role: str = 'user') -> Turn:
        self.last_id += 1
        turn = Turn(self.last_id, time.time() if at is None else at, role)
        self.turns.append(turn)
        self._trim()
        return turn

    def complete(self, turn: Turn, text: str, speaker=None, label='不明', sure=False) -> None:
        if turn.ready.is_set():
            return
        turn.text = text.strip()[:16000]
        turn.clipped = len(text.strip()) > 16000
        turn.speaker, turn.label, turn.sure = speaker, label, sure
        turn.ready.set()
        if turn.id > self.dropped_through:
            self._chars += len(turn.text)
            self._trim()

    def _trim(self) -> None:
        while self.turns and (len(self.turns) > self.max_turns or self._chars > self.max_chars):
            turn = self.turns.pop(0)
            self._chars -= len(turn.text)
            self.dropped_through = turn.id
            turn.ready.set()

    def between(self, after: int = 0, through: int | None = None) -> list[Turn]:
        return [t for t in self.turns if t.id > after and (through is None or t.id <= through)]

    def settled_through(self) -> int:
        # 確定前の発言を飛び越してカーソルを進めない。
        # 書き起こし失敗で全機能が止まらないよう、20秒を超えた区間は欠落として進む。
        return next((t.id - 1 for t in self.turns if not t.ready.is_set() and time.time() - t.at < 20), self.last_id)

    async def wait_pending(self, after: int, through: int, timeout: float = 5.0) -> None:
        pending = [t.ready.wait() for t in self.between(after, through) if not t.ready.is_set()]
        if pending:
            try:
                await asyncio.wait_for(asyncio.gather(*pending), timeout)
            except asyncio.TimeoutError:
                pass  # 読めなかったことは利用側へ明示する。通常の返答は待たせない。

    def on_split(self, old, new) -> None:
        for turn in reversed(self.turns):
            if turn.speaker is old:
                turn.speaker, turn.label, turn.sure = new, new.name or new.label, True
                return

    def personal_lines(self, through: int | None = None):
        return [(t.owner, t.name, t.text) for t in self.between(through=through)
                if t.ready.is_set() and t.text]

    def search(self, query: str, first_id: int = 0, last_id: int = 0) -> dict:
        """日本語の部分一致と文字 bigram。外部送信・追加のモデル呼び出しはしない。"""
        rows = list(self.turns)  # 検索はワーカースレッドで実行するため、対象範囲を固定する。
        terms = [normalize(s) for s in re.split(r'[\s、,]+', query[:200]) if normalize(s)]
        term_grams = [(term, grams(term)) for term in terms]
        if first_id > 0:
            selected = [t for t in rows if first_id <= t.id <= (last_id or first_id + 10)][:20]
        elif not terms:
            selected = rows[-12:]
        else:
            def score(t):
                body = normalize(t.text)
                return sum(5 if term in body else sum(g in body for g in parts) / len(parts)
                           for term, parts in term_grams) if t.ready.is_set() and t.text else 0
            ranked = sorted(((score(t), i) for i, t in enumerate(rows)), reverse=True)
            indices = set()
            for value, i in ranked:
                if value < 0.65:
                    break
                indices.update(range(max(0, i - 2), min(len(rows), i + 3)))
                if len(indices) >= 15:
                    break
            selected = [rows[i] for i in sorted(indices)]
        result, budget = [], 7000
        for t in selected:
            text = t.text[:min(1800, budget)]
            if budget <= 0:
                break
            result.append({'id': t.id, 'at': t.at, 'speaker': t.name,
                           'speaker_certain': t.sure if t.role == 'user' else True,
                           'status': 'ready' if t.ready.is_set() else 'pending', 'text': text,
                           'text_clipped': t.clipped or len(text) < len(t.text)})
            budget -= len(text)
        return {'scope': 'current_session', 'dropped_through': self.dropped_through,
                'pending_count': sum(not t.ready.is_set() for t in rows),
                'last_id': self.last_id, 'matches': result,
                'research': self.research.related(query, [r['id'] for r in result]),
                'research_dropped_through': self.research.dropped_through,
                'result_clipped': len(result) < len(selected)}


def normalize(text: str) -> str:
    return re.sub(r'\W+', '', unicodedata.normalize('NFKC', text).casefold())


def grams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}
