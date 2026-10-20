#!/usr/bin/env bash
# 表情ごとの声の聞き比べ：自宅の GPU サーバーで、同じ文を感情ごとのキャプションで 4 通り（絵文字の有無×効き方）に読み上げ、手元へ持ち帰る。
# 手元の server/agent/emotion.py の CAPTIONS を使う（デプロイしていない書きかけのキャプションも試せる）。
# 読み上げは動いている tts サービスに頼むので、会話中だと会話の声が少し遅れる。
# 使い方（Git Bash）：scripts/server/compare-emotion-voices.sh [取り数=2] [接続先]
# 接続先と SSH の鍵は deploy-server.sh と同じ（scripts/server/.env.local か環境変数。引数があれば引数）。
# 出力：.local/emotion-voices/<日時>/index.html（Git の外）
set -euo pipefail
TAKES="${1:-2}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${2:-}"
OUT="$ROOT/.local/emotion-voices/$(date +%Y%m%d-%H%M%S)"
TMP="/tmp/ciel-emotion-voices-$$"

tar -C "$ROOT/server" -cf - tts-irodori/compare_emotions.py agent/emotion.py \
  | "${SSH[@]}" "mkdir -p $TMP && cd $TMP && tar xf -"
"${SSH[@]}" "cd $TMP && python3 tts-irodori/compare_emotions.py agent/emotion.py out $TAKES"
mkdir -p "$OUT"
"${SSH[@]}" "cd $TMP/out && tar cf - . && rm -rf $TMP" | tar -C "$OUT" -xf -
echo "$OUT/index.html"
