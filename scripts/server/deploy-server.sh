#!/usr/bin/env bash
# サーバー一式（server/：会話サーバー・読み上げ・声質変換・DB）を自宅の GPU サーバーへ送り、Docker Compose で起動し直す。
# リポジトリ全体は送らない。.env（秘密情報）と data/（モデル・参照音声）は送らず、上書きもしない。
# サーバーの上での手順は server/deploy-remote.sh（DB のパスワードが無ければ作る、以前の構成の片付け）。
# 使い方（Git Bash）：scripts/server/deploy-server.sh [--dev] [接続先]
#   --dev … 開発用（~/work/ciel-companion-dev/server）へ送り、開発用の会話サーバーだけを作り直す（server/compose.dev.yaml）。
#           本番の会話サーバーには触らない。本番の compose.yaml は送らない（開発用の場所で本番を作り直さないように）
# 接続先と SSH の鍵は scripts/server/.env.local（見本は .env.example）か環境変数で決める。引数があれば引数を使う。
set -euo pipefail
MODE=prod
if [ "${1:-}" = --dev ]; then MODE=dev; shift; fi
MINECRAFT=
if [ "${1:-}" = --minecraft ]; then
  [ "$MODE" = dev ] || { echo '--minecraft requires --dev'; exit 2; }
  MINECRAFT=minecraft
  shift
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "$MODE" = dev ] && [ -z "$MINECRAFT" ]; then
  PYTHON="$ROOT/.venv/Scripts/python.exe"
  [ -f "$PYTHON" ] || PYTHON="$ROOT/.venv/bin/python"
  [ -f "$PYTHON" ] || PYTHON=python3
  ARGS=(--dev)
  if [ -n "${1:-}" ]; then ARGS+=(--host "$1"); fi
  exec "$PYTHON" "$ROOT/scripts/server/deploy-agent.py" "${ARGS[@]}"
fi
source "$ROOT/scripts/server/ssh-target.sh" "${1:-}"

if [ $MODE = dev ]; then
  DEST='~/work/ciel-companion-dev/server'
  EXCLUDES=(--exclude=./compose.yaml)
else
  DEST='~/work/ciel-companion/server'
  EXCLUDES=()
fi
tar -C "$ROOT/server" -cf - --exclude=.env --exclude=.env.shared --exclude=.env.dev --exclude=.env.minecraft --exclude=__pycache__ --exclude=node_modules --exclude=data ${EXCLUDES[@]+"${EXCLUDES[@]}"} . \
  | "${SSH[@]}" "mkdir -p $DEST && cd $DEST && tar xf -"
"${SSH[@]}" "bash $DEST/deploy-remote.sh $([ $MODE = dev ] && echo dev) $MINECRAFT"
echo DEPLOY_SERVER_DONE
