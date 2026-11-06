#!/usr/bin/env bash
# Ciel_Debug を自宅サーバーのマイクラに入れて、体の技を 1 つ試す（Git Bash、リポジトリのルートで）。
#   .claude/skills/ciel-minecraft-debug/scripts/run.sh <技> '<引数の JSON>' [--tp "x y z"] [--give "item 数"]... [--clear] [--seconds 60]
#   例：run.sh collect '{"block":"oak_log","count":3}' --tp "8.5 71 43.7"
#       run.sh craft '{"item":"wooden_pickaxe","count":1}' --tp "17.5 67 41.3" --clear --give "oak_log 3"
# 体（server/minecraft/src）は、自宅サーバーの体のコンテナに配ってある版が動く。手元の変更を試すときは、先に体を配る。
# 終わったら、写したファイルとコンテナの中に残ったプロセスを必ず消す（docker exec を時間切れで止めても、中の node は残り、
# 固まったまま CPU を 3 コア分使い続けた。2026-11-06）。
set -euo pipefail
SKILL="${1:?技の名前}"; ARGS="${2:?引数の JSON}"; shift 2
TP=""; CLEAR=0; SECONDS_LIMIT=60; GIVES=()
while [ $# -gt 0 ]; do
  case "$1" in
    --tp) TP="$2"; shift 2 ;;
    --give) GIVES+=("$2"); shift 2 ;;
    --clear) CLEAR=1; shift ;;
    --seconds) SECONDS_LIMIT="$2"; shift 2 ;;
    *) echo "知らない引数：$1" >&2; exit 2 ;;
  esac
done
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" ""
BODY=ciel-minecraft-body-1; MC=ciel-minecraft-1; NAME=Ciel_Debug

"${SSH[@]}" "cat > /tmp/ciel-debug-bot.mjs" < "$HERE/debug-bot.mjs"
# 中で動くものを先に片付けてから始める（前の試しが残っていると、同じ名前で入れない）
KILL="docker exec $BODY node -e \"for (const d of require('fs').readdirSync('/proc')) { if (!/^[0-9]+\$/.test(d) || d === String(process.pid)) continue; try { if (require('fs').readFileSync('/proc/' + d + '/cmdline', 'utf8').includes('ciel-debug-bot')) { process.kill(Number(d), 'SIGKILL'); console.log('残っていた試しを止めた', d) } } catch {} }\""
REMOTE=$(cat <<EOF
set -u
$KILL
docker cp /tmp/ciel-debug-bot.mjs $BODY:/app/ciel-debug-bot.mjs
docker exec $MC rcon-cli "whitelist list" | grep -q $NAME || echo "注意：$NAME がホワイトリストにいない（docs/minecraft-design-ja.md の 12 章「初回」の 3）"
(docker exec -w /app -e SKILL='$SKILL' -e ARGS='$ARGS' -e WAIT_MS=8000 -e SECONDS_LIMIT=$SECONDS_LIMIT $BODY node ciel-debug-bot.mjs > /tmp/ciel-debug-bot.log 2>&1 &)
for i in \$(seq 1 20); do sleep 1; docker exec $MC rcon-cli list | grep -q $NAME && break; done
[ -n "$TP" ] && docker exec $MC rcon-cli "tp $NAME $TP"
[ $CLEAR = 1 ] && docker exec $MC rcon-cli "clear $NAME"
EOF
)
for g in "${GIVES[@]+"${GIVES[@]}"}"; do REMOTE+=$'\n'"docker exec $MC rcon-cli \"give $NAME $g\""; done
REMOTE+=$'\n'"for i in \$(seq 1 $((SECONDS_LIMIT + 15))); do sleep 1; grep -q '終わり\\|LIMIT\\|外された' /tmp/ciel-debug-bot.log && break; done"
REMOTE+=$'\n'"cat /tmp/ciel-debug-bot.log"
REMOTE+=$'\n'"sleep 2; $KILL"
REMOTE+=$'\n'"docker exec -u root $BODY rm -f /app/ciel-debug-bot.mjs; rm -f /tmp/ciel-debug-bot.mjs /tmp/ciel-debug-bot.log"
"${SSH[@]}" "$REMOTE"
