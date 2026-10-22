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
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${1:-}"

if [ $MODE = dev ]; then
  DEST='~/work/ciel-companion-dev/server'
  EXCLUDES=(--exclude=./compose.yaml)
else
  DEST='~/work/ciel-companion/server'
  EXCLUDES=()
fi
tar -C "$ROOT/server" -cf - --exclude=.env --exclude=.env.dev --exclude=__pycache__ --exclude=data ${EXCLUDES[@]+"${EXCLUDES[@]}"} . \
  | "${SSH[@]}" "mkdir -p $DEST && cd $DEST && tar xf -"
"${SSH[@]}" "bash $DEST/deploy-remote.sh $([ $MODE = dev ] && echo dev)"
echo DEPLOY_SERVER_DONE
