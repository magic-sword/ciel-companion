#!/usr/bin/env bash
# 動いているシエルの体の中を、一度だけ止めて読む（Git Bash、リポジトリのルートで）。
#   .claude/skills/ciel-minecraft-debug/scripts/peek.sh [path|bot] ['<式>']
# 体の node にデバッガーの入口を開く（SIGUSR1。開いたままになるので、調べ終えたら体を入れ直して閉じる）。
# 入口はコンテナの中の 127.0.0.1:9229。体は host のネットワークなので、自宅サーバーの中からだけ届く。
# 9229 を別の node（残った試し）が使っていると、そちらを読んでしまう。先に run.sh の片付けか、下の確かめで消す。
set -euo pipefail
WHERE="${1:-path}"; EXPR="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" ""
BODY=ciel-minecraft-body-1
"${SSH[@]}" "cat > /tmp/ciel-peek.mjs" < "$HERE/peek.mjs"
"${SSH[@]}" "set -u
docker exec $BODY node -e \"for (const d of require('fs').readdirSync('/proc')) { if (!/^[0-9]+\\\$/.test(d) || d === '1' || d === String(process.pid)) continue; try { const c = require('fs').readFileSync('/proc/' + d + '/cmdline', 'utf8'); if (c.startsWith('node')) console.log('注意：体のほかに node が動いている', d, c.replace(/\\0/g, ' ')) } catch {} }\"
docker exec $BODY node -e \"process.kill(1, 'SIGUSR1')\"
sleep 1
docker cp /tmp/ciel-peek.mjs $BODY:/app/ciel-peek.mjs
docker exec -w /app -e WHERE='$WHERE' -e EXPR='$EXPR' $BODY node ciel-peek.mjs || true
docker exec -u root $BODY rm -f /app/ciel-peek.mjs; rm -f /tmp/ciel-peek.mjs"
