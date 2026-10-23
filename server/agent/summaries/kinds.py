"""項目の種類。種類はコードで決め、テンプレートは種類を組み合わせて見出しを作る。
モデルが返した項目は clean で形を整え、決まった欄だけ残す（知らない欄・長すぎる文字は捨てる）。"""
from research import web_url

KINDS = ('point', 'topic', 'decision', 'action', 'question', 'finding', 'goal', 'idea')
MAX_TEXT = 400
MAX_POINTS = 12


def _text(value, limit: int = MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ''


def clean(kind: str, raw, allowed_urls: set[str] | None = None) -> dict | None:
    """モデルが返した 1 項目を、種類の形にする。本文が無ければ None。
    発見（finding）の出典は、調べた記録にある URL だけ残す（モデルが作った URL を出さない）"""
    if not isinstance(raw, dict) or kind not in KINDS:
        return None
    text = _text(raw.get('text'))
    if not text:
        return None
    item = {'text': text}
    if kind == 'topic':
        points = raw.get('points') if isinstance(raw.get('points'), list) else []
        item['points'] = [p for p in (_text(p, 300) for p in points) if p][:MAX_POINTS]
    elif kind == 'action':
        item['who'], item['due'] = _text(raw.get('who'), 60), _text(raw.get('due'), 60)
        item['done'] = raw.get('done') is True
    elif kind == 'goal':
        item['status'] = _text(raw.get('status'), 20)
    elif kind == 'finding':
        sources = raw.get('sources') if isinstance(raw.get('sources'), list) else []
        item['sources'] = [{'title': _text(s.get('title'), 200) or s['url'], 'url': s['url']}
                           for s in sources if isinstance(s, dict) and isinstance(s.get('url'), str)
                           and web_url(s['url']) and (allowed_urls is None or s['url'] in allowed_urls)][:4]
    return item


def merge(kind: str, old: dict, change, allowed_urls: set[str] | None = None) -> dict | None:
    """直す差分：書かれた欄だけ変える"""
    if not isinstance(change, dict):
        return None
    return clean(kind, {**old, **{k: v for k, v in change.items() if k != 'id'}}, allowed_urls)


def render(kind: str, item: dict) -> list[str]:
    """Markdown の行。会議の議事録は、以前の議事録（minutes.md の JSON から作っていた形）と同じ書き方にする"""
    text = item['text']
    if kind == 'topic':
        return [f'### {text}', *(f'- {p}' for p in item.get('points', []))]
    if kind == 'action':
        who, due = item.get('who', ''), item.get('due', '')
        line = f'- {text.rstrip("。")}' + (f'（{who}' if who else '（担当未定') + (f'、{due} まで）' if due else '）')
        return [line + ('（済み）' if item.get('done') else '')]
    if kind == 'goal' and item.get('status'):
        return [f'- {text}（{item["status"]}）']
    if kind == 'finding' and item.get('sources'):
        return [f'- {text} ' + ' '.join(f'[{s["title"]}]({s["url"]})' for s in item['sources'])]
    return [f'- {text}']
