"""接続中だけの調査記録。会話本文・人物メモには混ぜない。"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
import re
import time
import json
from urllib.parse import urlsplit

from jst import JST


def web_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (len(value) <= 1500 and not any(c.isspace() or ord(c) < 32 for c in value)
                and url.scheme in ('http', 'https') and bool(url.hostname)
                and not url.username and not url.password)
    except ValueError:
        return False


@dataclass
class Research:
    id: int
    question: str
    requested_at: float
    request_turn_id: int | None
    call_id: str
    status: str = 'pending'
    checked_at: float | None = None
    summary: str = ''
    sources: list[dict] = field(default_factory=list)
    answer_turn_ids: list[int] = field(default_factory=list)
    clipped: bool = False

    def payload(self) -> dict:
        result = asdict(self)
        for key in ('requested_at', 'checked_at'):
            if result[key] is not None:
                result[key] = datetime.fromtimestamp(result[key], JST).isoformat()
        return result


class ResearchBook:
    def __init__(self, max_records: int = 50, max_chars: int = 200_000):
        self.records: list[Research] = []
        self.last_id = self.dropped_through = 0
        self.max_records, self.max_chars = max_records, max_chars

    def begin(self, question, request_turn_id, call_id) -> Research:
        self.last_id += 1
        record = Research(self.last_id, question[:600], time.time(), request_turn_id, call_id)
        self.records.append(record)
        self.trim()
        return record

    def trim(self):
        def size(r):
            return len(r.question) + len(r.summary) + sum(len(s['title']) + len(s['url']) for s in r.sources)
        total = sum(size(r) for r in self.records)
        while self.records and (len(self.records) > self.max_records or total > self.max_chars):
            old = self.records.pop(0)
            self.dropped_through = old.id
            total -= size(old)

    def get(self, record_id: int):
        return next((r for r in self.records if r.id == record_id), None)

    def related(self, query: str, turn_ids: list[int]) -> list[dict]:
        terms = [t.casefold() for t in re.split(r'[\s、,]+', query[:200]) if t]
        ids = set(turn_ids)
        def score(r):
            linked = r.request_turn_id in ids or bool(ids.intersection(r.answer_turn_ids))
            matches = sum(t in (r.question + r.summary).casefold() for t in terms)
            return (10 if linked else 0) + matches
        ranked = sorted(self.records, key=lambda r: (score(r), r.id), reverse=True)
        results, budget = [], 7000
        for record in [r for r in ranked if not terms or score(r) > 0][:3]:
            result = record.payload()
            result['summary'] = record.summary[:900]
            result['sources'] = record.sources[:3]
            result['clipped'] |= len(record.summary) > 900 or len(record.sources) > 3
            if len(json.dumps(result, ensure_ascii=False)) > budget:
                result['summary'], result['sources'], result['clipped'] = record.summary[:200], [], True
            size = len(json.dumps(result, ensure_ascii=False))
            if size > budget:
                break
            results.append(result)
            budget -= size
        return results

    def link_answers(self, record: Research, history, items):
        source_ids = {item.id for item in items if getattr(item, 'role', None) == 'assistant'}
        added = [t.id for t in history.turns if t.source_id in source_ids]
        record.answer_turn_ids = list(dict.fromkeys([*record.answer_turn_ids, *added]))[-20:]


def packets(record: Research):
    """LiveKit の reliable パケット上限に収まるよう、本文と出典を分割する。"""
    data = record.payload()
    yield {'v': 1, 'type': 'research.result', 'id': record.id, 'question': record.question,
           'checked_at': data['checked_at'], 'status': record.status, 'clipped': record.clipped,
           'part_count': (len(record.summary) + 1499) // 1500}
    for i in range(0, len(record.summary), 1500):
        yield {'v': 1, 'type': 'research.text', 'id': record.id, 'part': i // 1500, 'text': record.summary[i:i + 1500]}
    for source in record.sources:
        yield {'v': 1, 'type': 'research.source', 'id': record.id, 'source': source}
    yield {'v': 1, 'type': 'research.complete', 'id': record.id}
