<#
.SYNOPSIS
  Codex（VS Code の Codex 拡張に入っている codex.exe）に、コマンドから依頼する。
.DESCRIPTION
  依頼文はファイルで渡す（日本語・改行をそのまま渡すため）。最後の返答を -Out のファイルに書き、
  全体のログを同じ名前の .log に書く。リポジトリへの書き込みを許可する（workspace-write）。承認は求めない。
  VS Code 側で同じ会話を開いていると resume できない（"already has an active writer"）。VS Code の Codex を閉じてから使う。
  使い方:
    新しい会話: powershell -File scripts/codex/run-codex.ps1 -PromptFile 依頼.md -Out 返答.md
    続き:       powershell -File scripts/codex/run-codex.ps1 -PromptFile 依頼.md -Out 返答.md -Resume <session id>
  session id は、ログの "session id:" の行に出る。
#>
param(
    [Parameter(Mandatory = $true)][string]$PromptFile,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Resume = '',
    [string]$Effort = 'high'
)
$ErrorActionPreference = 'Stop'
$codex = Get-ChildItem "$env:USERPROFILE\.vscode\extensions" -Directory -Filter 'openai.chatgpt-*' |
    Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'bin\windows-x86_64\codex.exe' } |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $codex) { throw 'codex.exe not found (VS Code の Codex 拡張が必要)' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$prompt = (Resolve-Path $PromptFile).Path
$outFull = [IO.Path]::GetFullPath($Out)
$log = [IO.Path]::ChangeExtension($outFull, '.log')
# PowerShell 5.1 は、外部コマンドの標準エラー出力をエラーとして扱うので、cmd でリダイレクトする（依頼文は stdin から）。
$opts = "-c sandbox_mode=`"workspace-write`" -c approval_policy=`"never`" -c model_reasoning_effort=`"$Effort`" -o `"$outFull`""
if ($Resume) {
    # resume は --color・-C を受け付けない
    $cmd = "`"$codex`" exec resume $Resume $opts - < `"$prompt`" > `"$log`" 2>&1"
} else {
    $cmd = "`"$codex`" exec -C `"$root`" --color never $opts - < `"$prompt`" > `"$log`" 2>&1"
}
Push-Location $root
try {
    cmd /c $cmd
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
$sid = Select-String -Path $log -Pattern 'session id:\s*(\S+)' | Select-Object -First 1
if ($sid) { Write-Output ('SESSION ' + $sid.Matches[0].Groups[1].Value) }
Write-Output "CODEX_DONE exit=$code out=$outFull log=$log"
exit $code
