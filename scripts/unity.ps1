param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $UnityArguments
)

$ErrorActionPreference = 'Stop'
$unityCommand = Get-Command unity -CommandType Application -ErrorAction SilentlyContinue
$unityCli = if ($unityCommand) { $unityCommand.Source } else {
    Join-Path $env:ProgramFiles 'Unity Hub/resources/unity.exe'
}
if (-not (Test-Path -LiteralPath $unityCli)) {
    throw 'Unity CLI was not found. Install or update Unity Hub.'
}

Push-Location (Join-Path $PSScriptRoot '../unity')
try {
    & $unityCli --no-banner @UnityArguments
    $unityExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $unityExitCode
