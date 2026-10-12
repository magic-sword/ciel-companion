#!/usr/bin/env bash
# 会話サーバー（server/agent）を自宅の GPU サーバーへ送り、Docker で起動し直す。
# リポジトリ全体は送らない。サーバー側の .env（秘密情報）は送らず、上書きもしない。
# 使い方（Git Bash）：scripts/server/deploy-agent.sh [ホスト=prog@192.168.1.15]
set -euo pipefail
HOST="${1:-prog@192.168.1.15}"
DEST='~/work/ciel-companion/server'
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SSH=(ssh -i "$HOME/.ssh/prog_rsa" -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null
     -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=ERROR "$HOST")

tar -C "$ROOT/server" -cf - --exclude=.env --exclude=__pycache__ agent \
  | "${SSH[@]}" "mkdir -p $DEST && cd $DEST && tar xf - && chmod 600 agent/.env 2>/dev/null; true"
"${SSH[@]}" "cd $DEST/agent && test -f .env || { echo '.env がない（.env.example をもとに作る）'; exit 1; }; docker compose up -d --build 2>&1 | tail -3"
echo DEPLOY_AGENT_DONE
