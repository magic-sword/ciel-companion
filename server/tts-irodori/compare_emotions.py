# -*- coding: utf-8 -*-
"""表情ごとの声の聞き比べ：同じ文を、感情ごとのキャプション（server/agent/emotion.py の CAPTIONS）で、4 通りに読み上げる。

4 通り = 文に感情の絵文字を入れるか × 効き方の比率（Irodori-TTS の既定か、キャプションを強めて参照音声を弱めるか）。
絵文字（EMOJI）と強めた効き方（STYLE）は emotion.py のもの。D が会話の設定（2026-10-18 に採用）。

GPU サーバーの上で、動いている読み上げサービス（127.0.0.1:8766）に頼む。Python の標準ライブラリだけで動く。
ふつうは手元から scripts/server/compare-emotion-voices.sh で動かす（このファイルと emotion.py を送り、結果を持ち帰る）。
使い方：python3 compare_emotions.py <emotion.py> <出力フォルダ> [取り数=2]
出力：<感情>_<通り>_<文の番号>_<取り>.wav と、並べて聞ける index.html
同じ文・同じ取りは、4 通りとも同じ種（seed）で読むので、違いは条件の差になる。取りを変えると種が変わる。
"""
import ast
import html
import json
import os
import re
import sys
import time
import urllib.request
import wave

URL = os.environ.get('CIEL_TTS_URL', 'http://127.0.0.1:8766/synthesize')
SENTENCES = [
    'ワタシ、今日はあなたとお話しできるのを、ずっと楽しみにしていたのです。',
    'えっ、それって本当なのですか？',
    'うーん、どうしたらいいのでしょう……。',
]
STYLE_NAMES = ('BASE', 'CAPTIONS', 'EMOJI', 'STYLE')   # emotion.py から読むもの
CONDITIONS = [   # （名前, 説明, 絵文字を入れるか, 効き方を STYLE にするか）
    ('a', '絵文字なし・既定の効き方', False, False),
    ('b', '絵文字あり', True, False),
    ('c', 'キャプション強め', False, True),
    ('d', '絵文字あり＋キャプション強め（会話の設定）', True, True),
]
END = re.compile(r'[。！？!?…]*$')


def read_settings(path: str) -> dict:
    """emotion.py を動かさずに（livekit などが要るので）、STYLE_NAMES の値だけを読む"""
    tree = ast.parse(open(path, encoding='utf-8').read())
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in STYLE_NAMES:
                src = ast.unparse(node.value)
                names[node.targets[0].id] = eval(src, {}, dict(names))
    return names


def with_emoji(text: str, emoji: str) -> str:
    m = END.search(text)
    return text[:m.start()] + emoji + text[m.start():]


def synthesize(text: str, caption: str, **options) -> tuple[bytes, int]:
    body = json.dumps({'text': text, 'caption': caption} | options, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(URL, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), int(r.headers.get('X-Sample-Rate', '48000'))


def write_wav(path: str, pcm: bytes, sr: int) -> None:
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)


def page(s: dict, takes: int) -> str:
    captions, emojis = s['CAPTIONS'], s['EMOJI']
    head = ''.join(f'<th>{html.escape(s)}</th>' for s in SENTENCES)
    nav = ' '.join(f'<a href="#{emo}">{emo}</a>' for emo in captions)
    sections = []
    for emo, cap in captions.items():
        rows = []
        for key, label, emoji, _ in CONDITIONS:
            cells = ''.join(
                '<td>' + ''.join(f'<audio controls preload="none" src="{emo}_{key}_{i + 1}_{t + 1}.wav"></audio>'
                                 for t in range(takes)) + '</td>'
                for i in range(len(SENTENCES)))
            mark = f' {emojis[emo]}' if emoji and emo in emojis else ''
            rows.append(f'<tr><th>{key.upper()}　{html.escape(label)}{mark}</th>{cells}</tr>')
        sections.append(f'<section id="{emo}"><h2>{emo}</h2><p class="cap">{html.escape(cap)}</p>'
                        f'<table><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
    strong = f'キャプション {s["STYLE"]["cfg_caption"]}・参照音声 {s["STYLE"]["cfg_speaker"]}'
    return f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>表情ごとの声 4 通り</title>
<style>
:root {{ --bg:#fff; --fg:#222; --sub:#666; --line:#ddd; --link:#2563eb; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1f; --fg:#eee; --sub:#aaa; --line:#444; --link:#8ab4ff; }} }}
body {{ background:var(--bg); color:var(--fg); font-family:system-ui,sans-serif; margin:16px; }}
nav {{ position:sticky; top:0; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--line); }}
nav a {{ color:var(--link); margin-right:10px; }}
section {{ margin:24px 0 32px; }}
table {{ border-collapse:collapse; }}
th, td {{ border:1px solid var(--line); padding:6px 8px; vertical-align:top; text-align:left; }}
thead th {{ font-weight:normal; font-size:13px; max-width:240px; }}
tbody th {{ white-space:nowrap; font-size:14px; }}
audio {{ display:block; width:220px; height:32px; margin:2px 0; }}
p {{ color:var(--sub); }}
.cap {{ font-size:13px; max-width:900px; }}
</style></head><body>
<h1>表情ごとの声 4 通り</h1>
<p>A 絵文字なし・既定の効き方／B 文に感情の絵文字を入れる／C キャプションを強め参照音声を弱める（{strong}。既定は 3.0・5.0）／D B と C の両方（いまの会話の設定）。
参照音声はどれも同じ。1 マスに {takes} 回分。同じ列・同じ段（上下の位置）の声は、4 通りとも同じ種で読んでいる。</p>
<nav>{nav}</nav>
{"".join(sections)}
</body></html>
'''


def main():
    src, out = sys.argv[1], sys.argv[2]
    takes = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    s = read_settings(src)
    os.makedirs(out, exist_ok=True)
    for emo, cap in s['CAPTIONS'].items():
        for key, _, emoji, styled in CONDITIONS:
            for i, text in enumerate(SENTENCES):
                for t in range(takes):
                    t0 = time.perf_counter()
                    pcm, sr = synthesize(with_emoji(text, s['EMOJI'].get(emo, '')) if emoji else text, cap,
                                         seed=100 * (i + 1) + t, **(s['STYLE'] if styled else {}))
                    write_wav(os.path.join(out, f'{emo}_{key}_{i + 1}_{t + 1}.wav'), pcm, sr)
                    print(f'{emo} {key} {i + 1}-{t + 1}  {time.perf_counter() - t0:.2f} 秒', flush=True)
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page(s, takes))


if __name__ == '__main__':
    main()
