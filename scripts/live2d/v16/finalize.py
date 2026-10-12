"""Record provenance and create review-only candidate boards; no artwork editing."""
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageChops

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / 'assets/ciel/generated/v16'
LAY = ROOT / 'assets/ciel/layers/v16'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')


prompts = {}
for entry in read(GEN / 'prior-generation-calls.json'):
    for match in re.finditer(r'store\("((?:choker|jacket)_prompt_\d+)"\s*,\s*("(?:[^"\\]|\\.)*")\)', entry['arguments']):
        prompts[match.group(1)] = json.loads(match.group(2))

# The preceding session prepared jacket_prompt_04 but did not call imagegen for it.
# This session's executed fourth call is recorded separately and takes its place.
current = read(GEN / 'current-generation.json')
records = []
ref = 'assets/ciel/generated/v16/inputs/'
refs = {
    'choker-01': [ref + 'choker-reference.png'],
    'jacket-01': [ref + 'jacket-reference.png', 'assets/ciel/master/ciel-upper-body-2x.png'],
    'jacket-02': [ref + 'jacket-reference.png', 'assets/ciel/generated/v16/parts/jacket-01.png'],
    'jacket-03': [ref + 'jacket-reference.png', 'assets/ciel/master/ciel-upper-body-2x.png'],
    'jacket-04': current['referenced_image_paths'],
}
for name in ['choker-01', 'jacket-01', 'jacket-02', 'jacket-03', 'jacket-04']:
    kind, number = name.split('-')
    path = GEN / 'parts' / (name + '.png')
    im = Image.open(path)
    prompt = current['prompt'] if name == 'jacket-04' else prompts[kind + '_prompt_' + number]
    records.append({'candidate': name, 'source': path.relative_to(ROOT).as_posix(),
                    'prompt': prompt, 'references': refs[name], 'transparent_background': True,
                    'selected': name in ('choker-01', 'jacket-03'),
                    'sha256': sha(path), 'size': list(im.size), 'mode': im.mode})
    assert im.mode == 'RGBA' and im.getchannel('A').getextrema() == (0, 255)
write_new(GEN / 'generation-log.json', {
    'generation_counts': {'choker': 1, 'jacket': 4, 'body': 0},
    'count_note': 'Includes four existing generated candidates from the preceding v16 session and one new jacket generation. An unexecuted prepared prompt is not counted.',
    'calls': records,
})

unchanged = {p: sha(ROOT / p) == digest for p, digest in read(GEN / 'preexisting-hashes.json').items()}
assert all(unchanged.values())
selected = {'choker.png': 'choker-01.png', 'jacket.png': 'jacket-03.png'}
for final, source in selected.items():
    assert sha(GEN / final) == sha(GEN / 'parts' / source)

placements = read(LAY / 'placement.json')
verified = {}
for name, spec in placements['transforms'].items():
    source = Image.open(ROOT / spec['source']).convert('RGBA')
    resized = source.resize(tuple(round(v * spec['uniform_scale']) for v in source.size), Image.Resampling.LANCZOS)
    expected = Image.new('RGBA', tuple(placements['canvas']))
    expected.alpha_composite(resized, tuple(spec['translate']))
    actual = Image.open(LAY / 'garments' / (name + '.png')).convert('RGBA')
    assert ImageChops.difference(expected, actual).getbbox(alpha_only=False) is None
    verified[name] = {'matches_uniform_placement_exactly': True,
                      'source_size': list(source.size), 'scaled_size': list(resized.size),
                      'scale': spec['uniform_scale'], 'translate': spec['translate']}
write_new(LAY / 'handoff-validation.json', {
    'preexisting_files_unchanged': unchanged,
    'selected_files_are_byte_identical_copies': selected,
    'placement_pixel_comparison': verified,
    'no_paint_mask_warp_color_cleanup_or_split': True,
})

font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
board = Image.new('RGB', (1600, 700), '#424966')
draw = ImageDraw.Draw(board)
for index in range(1, 5):
    im = Image.open(GEN / 'parts' / ('jacket-%02d.png' % index)).convert('RGBA')
    scale = 390 / im.width
    im = im.resize((390, round(im.height * scale)), Image.Resampling.LANCZOS)
    tile = Image.new('RGBA', im.size, '#424966')
    tile.alpha_composite(im)
    x = (index - 1) * 400
    draw.text((x + 10, 12), 'Jacket %02d%s' % (index, ' - SELECTED' if index == 3 else ''), font=font, fill='white')
    board.paste(tile.convert('RGB'), (x + 5, 60))
    # Additional enlarged upper-collar crop is a review image only.
    close = Image.open(GEN / 'parts' / ('jacket-%02d.png' % index)).convert('RGBA').crop((180, 0, 1260, 650))
    close = close.resize((390, round(close.height * 390 / close.width)), Image.Resampling.LANCZOS)
    tile = Image.new('RGBA', close.size, '#e6e9ef')
    tile.alpha_composite(close)
    board.paste(tile.convert('RGB'), (x + 5, 400))
board.save(GEN / 'proofs/jacket-candidates.png')

report = '''# v16 首輪・上着の一体絵

首輪は1回生成の第1案、上着は4回生成の第3案を採用。体は指定のv15生成原画を使用し、再生成していません。
前のv16作業で作成済みだった首輪1案・上着3案を引き継ぎ、今回追加した生成は上着の第4案1回です。準備だけで実行されていなかった旧第4案の指示文は回数に含めていません。

## 納品

- 原画: `../../generated/v16/choker.png`、`../../generated/v16/jacket.png`。採用候補からバイト単位で同一のコピーです。
- 配置済み: `garments/Body.png`、`garments/Choker.png`、`garments/Jacket.png`。すべて2172×2896、RGBA、透明背景。
- 配置設定: `placement.json`。元から存在した設定をそのまま使用。
- 全体比較: `../../generated/v16/proofs/comparison-full.png`
- 首〜肩比較: `../../generated/v16/proofs/comparison-neck-shoulders.png`
- 透明合成: `../../generated/v16/proofs/v16-composite.png`
- 配置パーツ一覧: `../../generated/v16/proofs/placed-garments.png`
- 上着候補一覧: `../../generated/v16/proofs/jacket-candidates.png`
- 指示文・参照・ハッシュ: `../../generated/v16/generation-log.json`

## 採用理由

首輪第1案は、前帯から左右の内壁、奥側の帯まで一つの楕円の輪として連続しています。中央の金具、二つのシアンの発光点、下がる丸い飾り、黒い当て布が一枚に描かれ、参照のデザインを保っています。

上着第1案は連続した襟と裏地を満たしますが、中央に白いベストのような見返しと腰の黒い帯が加わっています。第2案はそれが減った一方で、後ろ襟が高く、肩から外した着方より通常の着方に近く見えます。第3案は中央で低く下がる後ろ襟が左右のファーへつながり、袖も比較的下向きで、4案の中では元絵の着方に最も近いため採用しました。第4案は襟がつながっていますが、上腕外側の髪状の長い房と周囲の点が増えたため不採用です。

## 配置

座標はキャンバス左上が原点。各原画全体の左上を、同じ倍率で拡大縮小した後に指定位置へ移動しています。回転は0度、切り抜き・前後分割はありません。

| パーツ | 原画 | 縦横共通倍率 | 左上座標 |
|---|---|---:|---|
| Body | v15/parts/body-01.png | 1.10 | (553, 1286) |
| Choker | v16/choker.png | 0.33 | (875, 1327) |
| Jacket | v16/jacket.png | 1.61 | (-35, 1280) |

配置は元絵の首輪・肩・袖のおおよその位置に合わせています。生成形状と元絵の差を局所変形で合わせる処理はしていません。上着の袖先・外縁と体の下端にはキャンバス外に出る部分があります。完全な上着は原画PNGに残っています。

## 確認と残る問題

- 重ね順はv15b後ろ髪 → Body → v14cの表示中の顔・頭・首レイヤー → Jacket → Choker。v14cの旧Body・旧上着・旧首輪は除外しています。
- 前後未分割のため、上着の背中側のシアン裏地が胸の白い服・宝石を隠し、後ろ襟が首元と前髪の一部に重なります。首輪の奥側も首より手前に表示されています。この確認図は完成時の前後関係を表しません。Claude Codeで前後を分けて重ね順を設定する必要があります。
- 採用した上着第3案にも、両上腕外側に髪のように見える細長い白い房が残っています。袖口の内側も濃い空洞の影が弱く、シアンの面として見えます。
- ファーの量感・前端・袖の装飾位置は元絵と完全一致していません。首輪も元絵に比べ帯と飾りの比率に小さな差があります。均等拡大縮小・移動での配置のため、その差を残しています。
- 生成原画には輪郭周囲の微小な孤立点や半透明の縁が残っています。消去・マスク・色調整・描き足しは行っていません。
- 体はv15の生成原画そのものです。脇の追加やお腹の形状変更を含むv15/v15bの加工済みBodyは使っていません。
- ハッシュと画素比較により、採用原画のコピー一致、体の元画像一致、3配置レイヤーが均等拡大縮小と移動のみの結果に一致することを確認しました。開始時に存在したv16ファイルのハッシュも全件一致しています。詳細は`validation.json`と`handoff-validation.json`。
- 作業成果は指定の3つのv16ディレクトリ内に保存しています。画像生成ツールは指定保存先に対応せず、ツール管理の`C:/Users/prog/.codex/generated_images/`にも原画を自動保存しました。その原画をv16へコピーしています。既存ファイルは変更していません。

## 実行した画像生成の指示文（全文）

全呼び出しで`transparent_background=true`。第1〜3案の実行指示文は前のv16セッションの記録から回収しました。
'''
for item in records:
    report += '\n### ' + item['candidate'] + ('（採用）' if item['selected'] else '（不採用）') + '\n\n'
    report += '参照: ' + '、'.join('`' + p + '`' for p in item['references']) + '\n\n'
    report += '```text\n' + item['prompt'] + '\n```\n'
with (LAY / 'report.md').open('x', encoding='utf-8') as out:
    out.write(report)
print(json.dumps({'generations': {'choker': 1, 'jacket': 4, 'body': 0},
                  'preexisting_files_preserved': len(unchanged), 'placement_checks': verified}, indent=2))
