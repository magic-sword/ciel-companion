#!/usr/bin/env bash
# 自宅の GPU サーバーの上で、scripts/server/deploy-server.sh（.ps1）が送ったあとに動かす（このフォルダで）。
set -e
cd "$(dirname "$0")"
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
