# 会話サーバー（server/agent）を自宅の GPU サーバーへ送り、Docker で起動し直す（deploy-agent.sh の PowerShell 版）。
# Windows に標準で入っている ssh・scp・tar だけを使う（Git Bash は不要）。
# リポジトリ全体は送らない。サーバー側の .env（秘密情報）は送らず、上書きもしない。
# 使い方（PowerShell、リポジトリのルートで）：.\scripts\server\deploy-agent.ps1 [-HostName prog@192.168.1.15]
param([string] $HostName = 'prog@192.168.1.15')

$ErrorActionPreference = 'Stop'
$dest = 'work/ciel-companion/server'   # サーバーのホームからの場所
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$key = Join-Path $env:USERPROFILE '.ssh/prog_rsa'
$sshOptions = @('-i', $key, '-o', 'IdentitiesOnly=yes', '-o', 'UserKnownHostsFile=NUL',
    '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes', '-o', 'LogLevel=ERROR')

function Invoke-Native([string] $what, [scriptblock] $command) {
    & $command
    if ($LASTEXITCODE -ne 0) { throw "$what に失敗しました（終了コード $LASTEXITCODE）" }
}

# PowerShell 5.1 のパイプはバイナリを壊すので、いったん tar のファイルにしてから送る
$archive = Join-Path ([IO.Path]::GetTempPath()) ("ciel-agent-" + [guid]::NewGuid().ToString('N') + '.tar')
try {
    Invoke-Native 'まとめる' { tar.exe -C (Join-Path $root 'server') -cf $archive --exclude=.env --exclude=__pycache__ agent }
    Invoke-Native '送り先の作成' { ssh.exe @sshOptions $HostName "mkdir -p ~/$dest" }
    Invoke-Native '送る' { scp.exe -q @sshOptions $archive "${HostName}:$dest/agent-upload.tar" }
    Invoke-Native '展開' { ssh.exe @sshOptions $HostName "cd ~/$dest && tar xf agent-upload.tar && rm agent-upload.tar && (chmod 600 agent/.env 2>/dev/null; true)" }
    ssh.exe @sshOptions $HostName "cd ~/$dest/agent && test -f .env || exit 3; docker compose up -d --build 2>&1 | tail -3"
    if ($LASTEXITCODE -eq 3) { throw 'サーバーに .env がありません（.env.example をもとに作ってください）' }
    if ($LASTEXITCODE -ne 0) { throw "起動し直すのに失敗しました（終了コード $LASTEXITCODE）" }
    Write-Output 'DEPLOY_AGENT_DONE'
}
finally {
    Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
}
