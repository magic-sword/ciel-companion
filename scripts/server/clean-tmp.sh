#!/usr/bin/env bash
# 試験・計測で作った一時ファイルを消す。決まった場所だけを消す（ほかの場所は消さない）。
#   自宅サーバー：/tmp の直下の ciel-* のうち、接続した利用者のもの（試験用の会話サーバー・計測に渡したコードやログ）
#   手元（--local を付けたとき）：Claude Code のスクラッチパッドの中身だけ（…/Temp/claude/<作業>/<会話>/scratchpad）
# 使い方（Git Bash、リポジトリのルートで）：
#   scripts/server/clean-tmp.sh                         自宅サーバーの一時ファイルを消す
#   scripts/server/clean-tmp.sh --local <scratchpad>    あわせて、手元のスクラッチパッドの中身も消す
#   scripts/server/clean-tmp.sh --dry-run [...]         消すものを表示するだけ
# 接続先と SSH の鍵は deploy-server.sh と同じ（scripts/server/.env.local か環境変数）。
set -euo pipefail
DRY=0
LOCAL=''
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; shift ;;
    --local) LOCAL="${2:?--local にはスクラッチパッドのフォルダを渡す}"; shift 2 ;;
    *) echo "使い方：$0 [--dry-run] [--local <scratchpad>]" >&2; exit 2 ;;
  esac
done
# 手元のスクラッチパッドは、何かを消す前に場所を確かめる（形が違う場所は消さない）
DIR=''
if [ -n "$LOCAL" ]; then
  DIR="$(cd "$LOCAL" 2>/dev/null && pwd)" || DIR=''
  case "$DIR" in
    */Temp/claude/*/scratchpad) ;;
    *) echo "スクラッチパッドではないので消さない：$LOCAL" >&2; exit 2 ;;
  esac
fi
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/server/ssh-target.sh" ""

# 自宅サーバー：/tmp の直下の ciel-*、自分のものだけ（コンテナが中に作った root のファイルも、自分のフォルダの中なら消せる）
if [ $DRY = 1 ]; then
  "${SSH[@]}" "find /tmp -mindepth 1 -maxdepth 1 -name 'ciel-*' -user \"\$(id -un)\" -print"
else
  "${SSH[@]}" "find /tmp -mindepth 1 -maxdepth 1 -name 'ciel-*' -user \"\$(id -un)\" -print -exec rm -rf {} +" \
    | sed 's/^/消した（自宅サーバー）：/'
fi

# 手元：スクラッチパッドの中身だけ（場所は最初に確かめた）
if [ -n "$DIR" ]; then
  if [ $DRY = 1 ]; then
    find "$DIR" -mindepth 1 -maxdepth 1 -print
  else
    find "$DIR" -mindepth 1 -maxdepth 1 -print -exec rm -rf {} + | sed 's/^/消した（手元）：/'
  fi
fi
