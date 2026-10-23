"""まとめの下書きの送り先：Discord の Webhook（利用者だけが見るチャンネル）。送れなかったときの、発言をそのまま並べる形。"""
import json
from datetime import datetime

import requests

from summaries.state import day

DISCORD_LIMIT = 2000    # Discord のメッセージの本文の上限（文字）


def render_raw(conversation: list[dict], started: datetime | None = None, ended: datetime | None = None,
               heading: str | None = None) -> str:
    """要約できなかったとき：発言をそのまま並べる（heading を渡すと、途中までのまとめの後ろに付ける節にする）"""
    if heading:
        out = ['', heading]
    else:
        out = ['# 会話の記録（要約できなかったので、発言をそのまま並べています）',
               f'{day(started)} {started:%H:%M}〜{ended:%H:%M}', '']
    out += [f'- {c["time"]} {c["speaker"]}：{c["text"]}' for c in conversation]
    return '\n'.join(out) + '\n'


def post_discord(url: str, text: str, filename: str, label: str = '議事録') -> None:
    """下書きを Discord の Webhook へ送る。長いときは本文の頭だけ書いて、全文は Markdown のファイルで添付する。
    本文の @everyone などで通知が飛ばないように、メンションはすべて無効にする"""
    header = f'📝 {label}の下書きです。内容を確かめてから共有してください。'
    payload = {'username': 'シエル', 'allowed_mentions': {'parse': []}}
    body = f'{header}\n\n{text}'
    if len(body) <= DISCORD_LIMIT:
        r = requests.post(url, json={**payload, 'content': body}, timeout=20)
    else:
        title = text.split('\n', 2)[:2]
        payload['content'] = '\n'.join([header, '', *title, '', '全文は添付のファイルです。'])[:DISCORD_LIMIT]
        r = requests.post(url, data={'payload_json': json.dumps(payload, ensure_ascii=False)},
                          files={'files[0]': (filename, text.encode('utf-8'), 'text/markdown')}, timeout=30)
    r.raise_for_status()
