# scripts/server/*.sh から source する。接続先と SSH の引数を決める（PowerShell 版は ssh-target.ps1）。
# 優先順：スクリプトの引数 > 環境変数 > scripts/server/.env.local（見本は .env.example）。
# 使い方：source ssh-target.sh "<引数の接続先（空でよい）>" → $HOST と配列 SSH ができる。

_ciel_env_file="$(dirname "${BASH_SOURCE[0]}")/.env.local"
_ciel_read_env() {  # .env.local から 1 つの値を読む（source はしない）
  [ -f "$_ciel_env_file" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$_ciel_env_file" | tail -n 1 | tr -d '\r'
}

HOST="${1:-${CIEL_SERVER_HOST:-$(_ciel_read_env CIEL_SERVER_HOST)}}"
_ciel_key="${CIEL_SSH_KEY-$(_ciel_read_env CIEL_SSH_KEY)}"
if [ -z "$HOST" ]; then
  echo '接続先が決まっていません。scripts/server/.env.example を .env.local に写して CIEL_SERVER_HOST を書くか、引数で渡してください。' >&2
  exit 2
fi

# 初めてのサーバーは鍵を覚え、2 回目からは食い違えば止める（accept-new）
SSH=(ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o LogLevel=ERROR)
if [ -n "$_ciel_key" ]; then
  SSH+=(-i "${_ciel_key/#\~/$HOME}" -o IdentitiesOnly=yes)
fi
SSH+=("$HOST")
