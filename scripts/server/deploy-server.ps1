# サーバー一式（server/：会話サーバー・読み上げ・声質変換・DB）を自宅の GPU サーバーへ送り、Docker Compose で起動し直す（deploy-server.sh の PowerShell 版）。
# Windows に標準で入っている ssh・scp・tar だけを使う（Git Bash は不要）。
# リポジトリ全体は送らない。.env（秘密情報）と data/（モデル・参照音声）は送らず、上書きもしない。
# サーバーの上での手順は server/deploy-remote.sh（DB のパスワードが無ければ作る、以前の構成の片付け）。
# 使い方（PowerShell、リポジトリのルートで）：.\scripts\server\deploy-server.ps1 [-HostName prog@192.168.1.15]
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
$archive = Join-Path ([IO.Path]::GetTempPath()) ("ciel-server-" + [guid]::NewGuid().ToString('N') + '.tar')
try {
    Invoke-Native 'まとめる' { tar.exe -C (Join-Path $root 'server') -cf $archive --exclude=.env --exclude=__pycache__ --exclude=data . }
    Invoke-Native '送り先の作成' { ssh.exe @sshOptions $HostName "mkdir -p ~/$dest" }
    Invoke-Native '送る' { scp.exe -q @sshOptions $archive "${HostName}:$dest/server-upload.tar" }
    Invoke-Native '展開' { ssh.exe @sshOptions $HostName "cd ~/$dest && tar xf server-upload.tar && rm server-upload.tar" }
    Invoke-Native '起動し直す' { ssh.exe @sshOptions $HostName "bash ~/$dest/deploy-remote.sh" }
    Write-Output 'DEPLOY_SERVER_DONE'
}
finally {
    Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
}
