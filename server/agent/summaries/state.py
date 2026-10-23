"""まとめの中身：テンプレートの見出しごとに、ID の付いた項目を並べる。
ライブの更新は差分（apply）、終わりの清書は置き換え（replace）。ID が変わらないので、アプリは新しく増えた・変わった項目だけを光らせられる。"""
from datetime import datetime

from summaries import kinds
from summaries.templates import Template

MAX_ITEMS = 40          # 見出し 1 つあたり
MAX_OPS = 60            # 1 回の差分
WEEKDAYS = '月火水木金土日'


def day(at: datetime) -> str:
    """2026-10-16（金）の形（コンテナのロケールでは %a が英語になるので）"""
    return f'{at:%Y-%m-%d}（{WEEKDAYS[at.weekday()]}）'


def _line(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ''


class SummaryState:
    def __init__(self, template: Template) -> None:
        self.template = template
        self.title = self.summary = self.current_topic = ''
        self.attendees: list[str] = []
        self.items: dict[str, list[dict]] = {s.id: [] for s in template.sections}   # 項目は {'id', 'rev', 欄…}
        self.rev = 0            # 変わるたびに増える。項目の rev は、その項目が最後に変わったときの番号
        self.allowed_urls: set[str] = set()   # 発見の出典にしてよい URL（この会話で調べた記録の出典）
        self._next = 0

    def has_content(self) -> bool:
        return bool(self.title or self.summary or any(self.items.values()))

    def _find(self, item_id) -> tuple[str, int] | None:
        for section_id, items in self.items.items():
            for i, item in enumerate(items):
                if item['id'] == item_id:
                    return section_id, i
        return None

    def _new_id(self, section_id: str) -> str:
        self._next += 1
        return f'{section_id}-{self._next}'

    @staticmethod
    def _data(item: dict) -> dict:
        return {k: v for k, v in item.items() if k not in ('id', 'rev')}

    def apply(self, result) -> int:
        """ライブの差分（config/prompts/minutes_live.md の形）。変わった数を返す（知らない見出し・ID は飛ばす）"""
        if not isinstance(result, dict):
            return 0
        rev, changed = self.rev + 1, 0
        for key, limit in (('title', 60), ('current_topic', 80)):
            value = _line(result.get(key), limit)
            if value and value != getattr(self, key):
                setattr(self, key, value)
                changed += 1
        ops = result.get('ops') if isinstance(result.get('ops'), list) else []
        for op in ops[:MAX_OPS]:
            if not isinstance(op, dict):
                continue
            if op.get('op') == 'add':
                section = self.template.section(op.get('section'))
                if section is None or len(self.items[section.id]) >= MAX_ITEMS:
                    continue
                item = kinds.clean(section.kind, op.get('item'), self.allowed_urls)
                if item is None or any(i['text'] == item['text'] for i in self.items[section.id]):
                    continue
                self.items[section.id].append({'id': self._new_id(section.id), 'rev': rev, **item})
                changed += 1
                continue
            found = self._find(op.get('id'))
            if found is None:
                continue
            section_id, i = found
            if op.get('op') == 'remove':
                del self.items[section_id][i]
                changed += 1
            elif op.get('op') == 'update':
                old = self.items[section_id][i]
                new = kinds.merge(self.template.section(section_id).kind, self._data(old), op.get('item'), self.allowed_urls)
                if new is not None and new != self._data(old):
                    self.items[section_id][i] = {'id': old['id'], 'rev': rev, **new}
                    changed += 1
        if changed:
            self.rev = rev
        return changed

    def replace(self, result) -> None:
        """清書（config/prompts/minutes.md の形）で全部を置き換える。前の項目の ID を返した項目は、その ID を保つ"""
        if not isinstance(result, dict):
            return
        rev = self.rev + 1
        self.title = _line(result.get('title'), 60) or self.title
        self.summary = _line(result.get('summary'), 600)
        attendees = result.get('attendees') if isinstance(result.get('attendees'), list) else []
        self.attendees = [a for a in (_line(a, 40) for a in attendees) if a][:30]
        sections = result.get('sections') if isinstance(result.get('sections'), dict) else {}
        items, used = {}, set()
        for section in self.template.sections:
            out = []
            raw_items = sections.get(section.id) if isinstance(sections.get(section.id), list) else []
            for raw in raw_items[:MAX_ITEMS]:
                item = kinds.clean(section.kind, raw, self.allowed_urls)
                if item is None:
                    continue
                found = self._find(raw.get('id')) if raw.get('id') not in used else None
                if found is not None and found[0] == section.id:
                    old = self.items[section.id][found[1]]
                    out.append({'id': old['id'], 'rev': old['rev'] if self._data(old) == item else rev, **item})
                else:
                    out.append({'id': self._new_id(section.id), 'rev': rev, **item})
                used.add(out[-1]['id'])
            items[section.id] = out
        self.items = items
        self.rev = rev

    def for_model(self) -> dict:
        """モデルに渡す今の中身（ID 付き。rev は渡さない）"""
        return {'title': self.title, 'current_topic': self.current_topic,
                'sections': [{'id': s.id, 'label': s.label, 'kind': s.kind,
                              'items': [{'id': i['id'], **self._data(i)} for i in self.items[s.id]]}
                             for s in self.template.sections]}

    def for_app(self) -> dict:
        """アプリへ送る形。Unity の JsonUtility で読めるよう、項目の欄はどの種類でもそろえる"""
        def item(i: dict) -> dict:
            return {'id': i['id'], 'rev': i['rev'], 'text': i['text'], 'points': i.get('points', []),
                    'who': i.get('who', ''), 'due': i.get('due', ''), 'done': i.get('done', False),
                    'status': i.get('status', ''), 'sources': i.get('sources', [])}
        return {'title': self.title, 'summary': self.summary, 'current_topic': self.current_topic,
                'attendees': self.attendees, 'rev': self.rev,
                'sections': [{'id': s.id, 'label': s.label, 'kind': s.kind,
                              'items': [item(i) for i in self.items[s.id]]} for s in self.template.sections]}

    def render(self, started: datetime, ended: datetime) -> str:
        """Discord で読める Markdown"""
        out = [f'# {self.title or self.template.label}', f'{day(started)} {started:%H:%M}〜{ended:%H:%M}']
        if self.attendees:
            out.append('参加者：' + '、'.join(self.attendees))
        if self.summary:
            out += ['', '## 概要', self.summary]
        for section in self.template.sections:
            if self.items[section.id]:
                out += ['', f'## {section.label}']
                for item in self.items[section.id]:
                    out += kinds.render(section.kind, item)
        return '\n'.join(out) + '\n'
