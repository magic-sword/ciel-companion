#!/usr/bin/env bash
# デバッグ用の会話ログ（server/agent/debug_log.py）を、本番の会話サーバーで入れる・切る・取り出す。
# 入れると、次に始まる会話から残す（会話サーバーの再起動は要らない。いま続いている会話は残さない）。
# 使い方（Git Bash、リポジトリのルートで）：
#   scripts/server/debug-log.sh on       … 入れる
#   scripts/server/debug-log.sh off      … 切る（残したログは、決めた日数（既定 7 日）で消える）
#   scripts/server/debug-log.sh status   … 入っているか・残っているログ
#   scripts/server/debug-log.sh pull     … ログを手元の .local/debug-logs/ へ持ち帰る（Git の外）
#   scripts/server/debug-log.sh clear    … サーバーに残っているログを今すぐ消す
# 接続先と SSH の鍵は deploy-server.sh と同じ（scripts/server/.env.local か環境変数）。
set -euo pipefail
ACTION="${1:-status}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${2:-}"
DIR='~/work/ciel-companion/server/agent/data/debug'

case "$ACTION" in
  on)
    "${SSH[@]}" "mkdir -p $DIR && touch $DIR/ON && echo 'デバッグ用の会話ログ：入れた（次に始まる会話から残す）'" ;;
  off)
    "${SSH[@]}" "rm -f $DIR/ON && echo 'デバッグ用の会話ログ：切った'" ;;
  status)
    "${SSH[@]}" "if [ -f $DIR/ON ]; then echo '入っている'; else echo '切っている'; fi; ls -l $DIR 2>/dev/null | grep '\.jsonl' || echo '残っているログはない'" ;;
  pull)
    OUT="$ROOT/.local/debug-logs"
    mkdir -p "$OUT"
    "${SSH[@]}" "cd $DIR 2>/dev/null && ls *.jsonl >/dev/null 2>&1 && tar cf - *.jsonl" | tar -C "$OUT" -xf - || true
    ls -l "$OUT" | grep '\.jsonl' || echo '持ち帰るログはなかった' ;;
  clear)
    "${SSH[@]}" "rm -f $DIR/*.jsonl && echo 'サーバーのログを消した'" ;;
  *)
    echo "使い方：$0 on|off|status|pull|clear" >&2; exit 2 ;;
esac
