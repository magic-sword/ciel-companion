"""UnityのCielResearchCheckへ渡す、公開情報を模した合成パケットを生成する。"""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'server' / 'agent'))
from research import ResearchBook, packets

output = root / '.local' / 'research-check' / 'packets.jsonl'
output.parent.mkdir(parents=True, exist_ok=True)
record = ResearchBook().begin('出典表示のテスト', None, 'check')
record.status = 'completed'
record.checked_at = record.requested_at
record.summary = 'テスト本文😀' * 400
record.sources = [
    {'number': 1, 'title': 'テスト資料1', 'url': 'https://example.org/a'},
    {'number': 2, 'title': 'テスト資料2', 'url': 'https://example.org/b'},
]
output.write_text('\n'.join(json.dumps(p, ensure_ascii=False) for p in packets(record)), encoding='utf-8')
print(output)
