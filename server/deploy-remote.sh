#!/usr/bin/env bash
# 自宅の GPU サーバーの上で、scripts/server/deploy-server.sh が送ったあとに動かす（このフォルダで）。
#   bash deploy-remote.sh        本番（~/work/ciel-companion/server）：会話サーバー・読み上げ・DB を起動し直す
#   bash deploy-remote.sh dev    開発用（~/work/ciel-companion-dev/server）：開発用の会話サーバーだけを起動し直す（compose.dev.yaml）
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = dev ]; then
  PROD=../../ciel-companion/server
  # Migrate without loading production behavior into the development environment.
  python3 environment.py --prod-dir "$PROD" --dev-dir "$PWD"
  docker inspect ciel-db-1 >/dev/null 2>&1 || { echo '本番の DB のコンテナが動いていない'; exit 1; }
  # 覚えている人の記録：本番と同じデータベース ciel を、印で分けて使う（docs/services/shared-memory-ja.md）。
  # 開発中のコードが起動のときに表を作り替えるので、その前に毎回バックアップを取る（新しい 14 個を残す。Git・デプロイの外）
  BACKUPS=../../ciel-db-backups
  mkdir -p $BACKUPS && chmod 700 $BACKUPS
  docker exec ciel-db-1 pg_dump -U ciel -d ciel | gzip > $BACKUPS/ciel-$(date +%Y%m%d-%H%M%S).sql.gz
  ls -1t $BACKUPS/ciel-*.sql.gz | tail -n +15 | xargs -r rm -f
  echo "DB のバックアップ：$(ls -1t $BACKUPS/ciel-*.sql.gz | head -1)"
  docker compose -f compose.dev.yaml --env-file $PROD/.env.shared --env-file .env.dev up -d --build 2>&1 | tail -6
  exit 0
fi

python3 environment.py --prod-dir "$PWD"
# 以前の、サービスごとの compose.yaml で動いていたものを止めて片付ける（2026-10-15 にまとめた。一度だけ）
for d in agent tts-irodori voice-conversion; do
  if [ -f "$d/compose.yaml" ]; then (cd "$d" && docker compose down) && rm -f "$d/compose.yaml"; fi
done
docker compose --env-file .env.shared --env-file .env up -d --build 2>&1 | tail -8
