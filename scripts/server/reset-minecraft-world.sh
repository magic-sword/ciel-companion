#!/usr/bin/env bash
# 自宅サーバーの普段のマイクラのワールドを作り直す（Git Bash、リポジトリのルートで）。
#   scripts/server/reset-minecraft-world.sh [接続先]
# 種は server/compose.yaml の MINECRAFT_SEED の既定値（草原で原木が近い初期地点。docs/games/minecraft/minecraft-design-ja.md）。
# 別の種で作るときだけ、サーバーの server/.env.minecraft に MINECRAFT_SEED を書く。
#
# すること：
#   1. 体と、マイクラのサーバーを止める
#   2. 今のワールド（world・world_nether・world_the_end）と、体の拠点の記憶を、消さずに退避する
#      （サーバーの server/minecraft/world-resets/<日時>/。Git・デプロイの外）
#   3. サーバーの compose.yaml をリポジトリの版にそろえ、種を確かめてマイクラを起動する（新しいワールドができる）
#   4. ゲーム内の時間を止め（advance_time false）、昼（time set 6000）にする
#   5. 体を起動し、Ciel が入るのを待つ
# ホワイトリスト・管理者・サーバーの設定は data/ に残る。プレイヤーの持ち物と位置は、ワールドと一緒に新しくなる。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${1:-}"

# The server copy of compose.yaml is replaced only when it is the committed one (no edits there).
LOCAL=$(git -C "$ROOT" show HEAD:server/compose.yaml | sha256sum | cut -d' ' -f1)
REMOTE=$("${SSH[@]}" 'sha256sum ~/work/ciel-companion/server/compose.yaml' | cut -d' ' -f1)
if [ "$LOCAL" != "$REMOTE" ]; then
  git -C "$ROOT" show HEAD:server/compose.yaml | "${SSH[@]}" 'cat > /tmp/ciel-compose.yaml'
  "${SSH[@]}" 'cd ~/work/ciel-companion/server && cp compose.yaml compose.yaml.before-world-reset && mv /tmp/ciel-compose.yaml compose.yaml'
fi

"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd ~/work/ciel-companion/server
COMPOSE=(docker compose -p ciel --env-file .env.shared --env-file .env --env-file .env.minecraft -f compose.yaml)
[ -f compose.body-release.json ] && COMPOSE+=(-f compose.body-release.json)
SEED=$("${COMPOSE[@]}" --profile minecraft config --format json | python3 -c 'import json,sys;print(json.load(sys.stdin)["services"]["minecraft"]["environment"].get("SEED",""))')
[ -n "$SEED" ] || { echo 'compose.yaml に SEED が無い'; exit 1; }
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP=minecraft/world-resets/$STAMP
mkdir -p "$BACKUP" && chmod 700 minecraft/world-resets

"${COMPOSE[@]}" --profile minecraft stop minecraft-body minecraft
for d in world world_nether world_the_end; do
  [ -e minecraft/data/$d ] && mv minecraft/data/$d "$BACKUP/"
done
# The body's base memory belongs to the old world (its file is named by server address, not world).
docker run --rm -v ciel_minecraft-body-data:/body -v "$PWD/$BACKUP":/backup alpine sh -c \
  'mkdir -p /backup/body-data && for f in /body/base-*.json; do [ -e "$f" ] && mv "$f" /backup/body-data/; done; true'
echo "退避：$PWD/$BACKUP"

"${COMPOSE[@]}" --profile minecraft up -d --no-build minecraft
for i in $(seq 1 120); do
  docker logs --since 5m ciel-minecraft-1 2>&1 | grep -q 'Done (' && break
  sleep 2
done
docker exec ciel-minecraft-1 rcon-cli seed
docker exec ciel-minecraft-1 rcon-cli 'gamerule advance_time false'
docker exec ciel-minecraft-1 rcon-cli 'time set 6000'
"${COMPOSE[@]}" --profile minecraft up -d --no-build --no-deps minecraft-body
for i in $(seq 1 60); do
  docker exec ciel-minecraft-1 rcon-cli list 2>/dev/null | grep -q Ciel && break
  sleep 2
done
docker exec ciel-minecraft-1 rcon-cli list
docker exec ciel-minecraft-1 rcon-cli 'gamerule advance_time'
docker exec ciel-minecraft-1 rcon-cli 'time query daytime'
echo "期待した種：$SEED"
REMOTE
echo RESET_MINECRAFT_WORLD_DONE
