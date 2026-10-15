#!/usr/bin/env bash
# サーバー一式（server/：会話サーバー・読み上げ・声質変換・DB）を自宅の GPU サーバーへ送り、Docker Compose で起動し直す。
# リポジトリ全体は送らない。.env（秘密情報）と data/（モデル・参照音声）は送らず、上書きもしない。
# サーバーの上での手順は server/deploy-remote.sh（DB のパスワードが無ければ作る、以前の構成の片付け）。
# 使い方（Git Bash）：scripts/server/deploy-server.sh [ホスト=prog@192.168.1.15]
# PowerShell からは同じ処理の deploy-server.ps1 を使う（Git Bash は不要）。
set -euo pipefail
HOST="${1:-prog@192.168.1.15}"
DEST='~/work/ciel-companion/server'
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SSH=(ssh -i "$HOME/.ssh/prog_rsa" -o IdentitiesOnly=yes -o UserKnownHostsFile=/dev/null
     -o StrictHostKeyChecking=no -o BatchMode=yes -o LogLevel=ERROR "$HOST")

tar -C "$ROOT/server" -cf - --exclude=.env --exclude=__pycache__ --exclude=data . \
  | "${SSH[@]}" "mkdir -p $DEST && cd $DEST && tar xf -"
"${SSH[@]}" "bash $DEST/deploy-remote.sh"
echo DEPLOY_SERVER_DONE
