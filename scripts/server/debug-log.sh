#!/usr/bin/env bash
# デバッグ用の会話ログ（server/agent/debug_log.py）を、本番の会話サーバーで入れる・切る・取り出す。
# 入れると、次に始まる会話から残す（会話サーバーの再起動は要らない。いま続いている会話は残さない）。
# 使い方（Git Bash、リポジトリのルートで）：
#   scripts/server/debug-log.sh on       … 入れる
#   scripts/server/debug-log.sh off      … 切る（残したログは、決めた日数（既定 7 日）で消える）
#   scripts/server/debug-log.sh status   … 入っているか・残っているログ
#   scripts/server/debug-log.sh pull     … ログを手元の .local/debug-logs/（開発用は debug-logs-dev/）へ持ち帰る（Git の外）
#   scripts/server/debug-log.sh clear    … サーバーに残っているログを今すぐ消す
#   どれも --dev を付けると開発用の会話サーバー（compose.dev.yaml。いつも残している）が対象（例：debug-log.sh pull --dev）
# 接続先と SSH の鍵は deploy-server.sh と同じ（scripts/server/.env.local か環境変数）。
# サーバーの server/agent/data/ はコンテナが作ったので root のもの。ファイルの操作は、動いている会話サーバーのコンテナの中で行う。
set -euo pipefail
ACTION="${1:-status}"
CONTAINER=ciel-agent-1
OUT_NAME=debug-logs
if [ "${2:-}" = --dev ]; then CONTAINER=ciel-dev-agent-dev-1; OUT_NAME=debug-logs-dev; set -- "$1" "${@:3}"; fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${2:-}"
IN_AGENT="docker exec -i $CONTAINER sh -c"
DIR=/app/data/debug
if [ "$CONTAINER" != ciel-agent-1 ] && { [ "$ACTION" = on ] || [ "$ACTION" = off ]; }; then
  echo '開発用の会話サーバーは、いつも残している（入れる・切るは要らない）'; exit 0
fi

case "$ACTION" in
  on)
    "${SSH[@]}" "$IN_AGENT 'mkdir -p $DIR && touch $DIR/ON' && echo 'デバッグ用の会話ログ：入れた（次に始まる会話から残す）'" ;;
  off)
    "${SSH[@]}" "$IN_AGENT 'rm -f $DIR/ON' && echo 'デバッグ用の会話ログ：切った'" ;;
  status)
    if [ "$CONTAINER" != ciel-agent-1 ]; then
      echo 'いつも残している（開発用）'
      "${SSH[@]}" "$IN_AGENT 'ls -l $DIR 2>/dev/null | grep \"\\.jsonl\" || echo 残っているログはない'"
    else
      "${SSH[@]}" "$IN_AGENT 'if [ -f $DIR/ON ]; then echo 入っている; else echo 切っている; fi; ls -l $DIR 2>/dev/null | grep \"\\.jsonl\" || echo 残っているログはない'"
    fi ;;
  pull)
    OUT="$ROOT/.local/$OUT_NAME"
    mkdir -p "$OUT"
    "${SSH[@]}" "$IN_AGENT 'cd $DIR 2>/dev/null && ls *.jsonl >/dev/null 2>&1 && tar cf - *.jsonl'" | tar -C "$OUT" -xf - 2>/dev/null || true
    ls -l "$OUT" | grep '\.jsonl' || echo '持ち帰るログはなかった' ;;
  clear)
    "${SSH[@]}" "$IN_AGENT 'rm -f $DIR/*.jsonl' && echo 'サーバーのログを消した'" ;;
  *)
    echo "使い方：$0 on|off|status|pull|clear" >&2; exit 2 ;;
esac
