param([string]$GimpPath, [ValidateSet('Remake', 'Legacy')][string]$Study = 'Remake', [switch]$Publish)
$ErrorActionPreference = 'Stop'
if ($Publish -and $Study -ne 'Remake') { throw '-Publish is available only for Remake.' }
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
    $scriptName = if ($Study -eq 'Legacy') { 'build_face_registration.py' } else { 'build_face_remake.py' }
    $batchCode = "exec(open('scripts/gimp/$scriptName', encoding='utf-8').read())"
    $batchStarted = Get-Date
    & $GimpPath --new-instance --no-data --no-fonts --no-splash --console-messages --batch-interpreter=python-fu-eval --batch $batchCode --quit
    if ($LASTEXITCODE -ne 0) { throw "GIMP batch failed: $LASTEXITCODE" }
    if ($Study -eq 'Remake') {
        # GIMP may exit 0 after a Python batch exception. Require the fresh final
        # report, written only after the expression exports and assertions finish.
        $artifactRoot = Join-Path $projectRoot 'assets/private/ciel/live2d/gimp/face-remake-v2'
        $reportFile = Get-Item -LiteralPath (Join-Path $artifactRoot 'verification.json')
        $report = Get-Content -LiteralPath $reportFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($reportFile.LastWriteTime -lt $batchStarted -or
            $report.expression_atlas.blink_levels -ne 33 -or
            $report.expression_atlas.mouth_levels -ne 33 -or
            $report.expression_atlas.neutral_equal -ne $true) {
            throw 'Remake batch did not produce a fresh, complete verification report.'
        }
        if ($Publish) {
            $publicRoot = Join-Path $projectRoot 'docs/assets/ciel/production'
            foreach ($artifact in @('blink-atlas', 'mouth-atlas', 'comparison', 'combined-comparison')) {
                Copy-Item -LiteralPath (Join-Path $artifactRoot "$artifact.png") -Destination (Join-Path $publicRoot "ciel-face-remake-v2-$artifact.png")
            }
            Copy-Item -LiteralPath $reportFile.FullName -Destination (Join-Path $publicRoot 'ciel-face-remake-v2-report.json')
        }
    }
} finally {
    Pop-Location
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
