param(
    [string] $Python = 'python',
    [ValidateSet('unit', 'db', 'all')] [string] $Suite = 'unit',
    [ValidateSet('docker', 'external')] [string] $DbMode = 'docker'
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'run-regression.py') --suite $Suite --db-mode $DbMode
exit $LASTEXITCODE
