param([string]$GimpPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $GimpPath) {
    $GimpPath = Join-Path $env:LOCALAPPDATA 'Programs\GIMP 3\bin\gimp-console-3.2.exe'
}
if (-not (Test-Path -LiteralPath $GimpPath)) { throw 'Specify -GimpPath with the GIMP 3 console executable.' }
$settings = @{
    GIMP3_DIRECTORY = Join-Path $projectRoot '.local/gimp-production/profile'
    GIMP3_CACHEDIR = Join-Path $projectRoot '.local/gimp-production/cache'
    GIMP3_TEMPDIR = Join-Path $projectRoot '.local/gimp-production/temp'
    CIEL_PROJECT_ROOT = $projectRoot
}
$previous = @{}
foreach ($key in $settings.Keys) {
    $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    if ($key -ne 'CIEL_PROJECT_ROOT') { New-Item -ItemType Directory -Path $settings[$key] -Force | Out-Null }
    [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
}
try {
    Push-Location $projectRoot
    $batchCode = "exec(open('scripts/gimp/build_face_registration.py', encoding='utf-8').read())"
    & $GimpPath --new-instance --no-data --no-fonts --no-splash --console-messages --batch-interpreter=python-fu-eval --batch $batchCode --quit
    if ($LASTEXITCODE -ne 0) { throw "GIMP batch failed: $LASTEXITCODE" }
} finally {
    Pop-Location
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
