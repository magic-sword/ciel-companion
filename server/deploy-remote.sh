#!/usr/bin/env bash
# 自宅の GPU サーバーの上で、scripts/server/deploy-server.sh が送ったあとに動かす（このフォルダで）。
#   bash deploy-remote.sh        本番（~/work/ciel-companion/server）：会話サーバー・読み上げ・DB を起動し直す
#   bash deploy-remote.sh dev    開発用（~/work/ciel-companion-dev/server）：開発用の会話サーバーだけを起動し直す（compose.dev.yaml）
set -e
cd "$(dirname "$0")"

if [ "${1:-}" = dev ]; then
  PROD=../../ciel-companion/server
  test -f $PROD/agent/.env -a -f $PROD/.env || { echo '本番の agent/.env・.env がない（先に本番をデプロイする）'; exit 1; }
  docker inspect ciel-db-1 >/dev/null 2>&1 || { echo '本番の DB のコンテナ（ciel-db-1）が動いていない'; exit 1; }
  # 開発用の議事録の送り先。無ければ空のファイルを作る（空ならサーバーに保存するだけ。Webhook は利用者が書く）
  if [ ! -f .env.dev ]; then
    (umask 077; printf '# 開発用の Discord のチャンネルの Webhook の URL（Git に入れない）\nCIEL_DEV_DISCORD_WEBHOOK=\n' > .env.dev)
    echo '開発用の設定を作った（server/.env.dev。議事録の送り先は空）'
  fi
  # 覚えている人の記録：本番と同じ DB のコンテナの中の、別のデータベース
  if ! docker exec ciel-db-1 psql -U ciel -d ciel -tAc "SELECT 1 FROM pg_database WHERE datname = 'ciel_dev'" | grep -q 1; then
    docker exec ciel-db-1 createdb -U ciel ciel_dev
    echo '開発用のデータベース ciel_dev を作った'
  fi
  docker compose -f compose.dev.yaml --env-file $PROD/.env --env-file .env.dev up -d --build 2>&1 | tail -6
  exit 0
fi

test -f agent/.env || { echo 'agent/.env がない（agent/.env.example をもとに作る）'; exit 1; }
chmod 600 agent/.env
# 以前の、サービスごとの compose.yaml で動いていたものを止めて片付ける（2026-10-15 にまとめた。一度だけ）
for d in agent tts-irodori voice-conversion; do
  if [ -f "$d/compose.yaml" ]; then (cd "$d" && docker compose down) && rm -f "$d/compose.yaml"; fi
done
# DB のパスワード。無ければ作る（画面には出さない）
if [ ! -f .env ]; then
  (umask 077; printf 'CIEL_DB_PASSWORD=%s\n' "$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" > .env)
  echo 'DB のパスワードを作った（server/.env）'
fi
docker compose up -d --build 2>&1 | tail -8
