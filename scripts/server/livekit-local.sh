#!/usr/bin/env bash
# 家の中だけの LiveKit と試験用の会話サーバーを、自宅サーバーで起動・停止する（Git Bash、リポジトリのルートで）。
#   scripts/server/livekit-local.sh start    今の開発の会話サーバーと同じ版で起動する（初回は鍵を作る）
#   LIVEKIT_LOCAL_REVISION=<コミット> scripts/server/livekit-local.sh start
#                                            開発へ配布したことのある別の版で起動する（変更の前後を比べるとき）
#   scripts/server/livekit-local.sh measure  試験・測定用に起動する（start と同じ版で、返事の役目も含めて推論をすべて共有GPUのローカルへ。
#                                            料金がかからない。終わったら start で普段の設定に戻す）
#   CIEL_RECALL_MIND=0 scripts/server/livekit-local.sh measure
#                                            心の見極めを切って起動する（ありとなしの比較）
#   CIEL_MIND_IDEAS=1 scripts/server/livekit-local.sh measure   # 心が話したいことと点も出す（段階1。記録だけ）
#   scripts/server/livekit-local.sh stop     止める（普段の開発・本番には触らない）
#   scripts/server/livekit-local.sh status   動いているか、アプリに入れるトークンの取得先
# 置き場所は開発（~/work/ciel-companion-dev/server）。compose.livekit-local.yaml と livekit-local/ をそこへ送る。
# 家の中のアドレスは本番の server/.env.minecraft の MC_BIND。防壁（ufw）でポート 7880〜7883 を家の中から通す設定は、
# 管理者の権限が要るので、この手順に含めない（docs/operations/local-livekit-ja.md）。
set -euo pipefail
ACTION="${1:-status}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" "${2:-}"
DEST='~/work/ciel-companion-dev/server'

if [ "$ACTION" = start ] || [ "$ACTION" = measure ]; then
  tar -C "$ROOT/server" -cf - compose.livekit-local.yaml livekit-local | "${SSH[@]}" "cd $DEST && tar xf -"
fi

REVISION=${LIVEKIT_LOCAL_REVISION:+$(git -C "$ROOT" rev-parse --verify "$LIVEKIT_LOCAL_REVISION^{commit}")}
"${SSH[@]}" "ACTION=$ACTION REVISION=$REVISION CIEL_RECALL_MIND=${CIEL_RECALL_MIND:-1} CIEL_RECALL_MIND_SPEAKING=${CIEL_RECALL_MIND_SPEAKING:-1} CIEL_MIND_IDEAS=${CIEL_MIND_IDEAS:-0} bash -s" <<'REMOTE'
set -euo pipefail
cd ~/work/ciel-companion-dev/server
PROD=../../ciel-companion/server
ENV=.env.livekit-local
if [ ! -f "$ENV" ]; then
  [ "$ACTION" = start ] || [ "$ACTION" = measure ] || { echo '家の中の LiveKit はまだ作っていない（start で作る）'; exit 0; }
  BIND=$(sed -n 's/^MC_BIND=//p' "$PROD/.env.minecraft" | tail -n 1)
  [ -n "$BIND" ] || { echo '本番の .env.minecraft に MC_BIND（家の中の IPv4）が無い'; exit 1; }
  umask 077
  python3 - "$BIND" > "$ENV" <<'PY'
import secrets, sys
print(f'LIVEKIT_LOCAL_BIND={sys.argv[1]}')
print(f'LIVEKIT_LOCAL_KEY=ciel{secrets.token_hex(6)}')
print(f'LIVEKIT_LOCAL_SECRET={secrets.token_urlsafe(32)}')
PY
fi
set -a; . "./$ENV"; set +a
if [ "$ACTION" = measure ]; then
  # 試験・測定：.env.livekit-local の OpenAI の役目（普段の会話用）を使わない。Compose の補間では、
  # この環境変数が --env-file の値より優先される（compose.livekit-local.yaml の agent-local）
  export CIEL_OPENAI_ROLES= CIEL_LLM_BACKEND=local
fi
if [ -n "$REVISION" ]; then
  # deploy-agent.py が残した、その版のイメージと設定
  REV=${REVISION:0:12}
  export CIEL_LOCAL_AGENT_IMAGE=ciel-dev-agent:$REV
  export CIEL_LOCAL_AGENT_CONFIG=$(ls -d "$PWD"/data/deployments/agent-$REV*/release/server/agent/config 2>/dev/null | tail -n 1)
else
  export CIEL_LOCAL_AGENT_IMAGE=$(docker inspect ciel-dev-agent-dev-1 --format '{{.Config.Image}}' 2>/dev/null || true)
  export CIEL_LOCAL_AGENT_CONFIG=$(docker inspect ciel-dev-agent-dev-1 --format '{{range .Mounts}}{{if eq .Destination "/app/config"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)
fi
COMPOSE=(docker compose -p ciel-dev --env-file "$PROD/.env.shared" --env-file .env.dev --env-file "$ENV"
         -f compose.dev.yaml -f compose.livekit-local.yaml)
case "$ACTION" in
  start|measure)
    [ -n "$CIEL_LOCAL_AGENT_IMAGE" ] && [ -n "$CIEL_LOCAL_AGENT_CONFIG" ]       || { echo '開発の会話サーバー（ciel-dev-agent-dev-1）が無いので、同じ版と設定が分からない'; exit 1; }
    "${COMPOSE[@]}" up -d --no-build --no-deps --force-recreate livekit-local token-local agent-local 2>&1 | tail -6
    for i in $(seq 1 60); do
      docker logs --since 2m ciel-dev-agent-local-1 2>&1 | grep -q 'registered worker' && break
      sleep 2
    done
    ;;
  stop)
    [ ! -f "$PROD/.env.livekit-production" ] || { echo '本番がこのLiveKitを使用中です。本番の接続先を戻してから停止してください。'; exit 1; }
    "${COMPOSE[@]}" stop livekit-local token-local agent-local 2>&1 | tail -4
    "${COMPOSE[@]}" rm -f livekit-local token-local agent-local >/dev/null 2>&1 || true
    ;;
esac
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'ciel-dev-(livekit|token|agent)-local' || echo '家の中の LiveKit は止まっている'
docker logs --since 5m ciel-dev-agent-local-1 2>&1 | grep -c 'registered worker' | sed 's/^/試験用の会話サーバーの worker 登録：/' || true
docker exec ciel-dev-agent-local-1 sh -c 'echo "試験用の会話サーバーの推論：backend=${CIEL_LLM_BACKEND:-?} OpenAIの役目=[${CIEL_OPENAI_ROLES}]（空ならすべてローカル） 心の見極め=${CIEL_RECALL_MIND:-1} 話している間も=${CIEL_RECALL_MIND_SPEAKING:-1} 話したいこと=${CIEL_MIND_IDEAS:-0}"' 2>/dev/null || true
echo "アプリのトークンの取得先：http://$LIVEKIT_LOCAL_BIND:7883/token"
REMOTE
