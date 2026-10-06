param([switch]$Publish)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$gimp=Join-Path $env:LOCALAPPDATA 'Programs\GIMP 3\bin\gimp-console-3.2.exe'
if(-not(Test-Path -LiteralPath $gimp)){throw 'GIMP 3 console executable not found.'}
$settings=@{
 CIEL_PROJECT_ROOT=$projectRoot
 CIEL_APPROVED_EYE_ATLAS='1'
 CIEL_CUBISM_SOFT_MASK='0'
 GIMP3_DIRECTORY=Join-Path $projectRoot '.local/gimp-production/profile'
 GIMP3_CACHEDIR=Join-Path $projectRoot '.local/gimp-production/cache'
 GIMP3_TEMPDIR=Join-Path $projectRoot '.local/gimp-production/temp'
}
$previous=@{}
foreach($key in $settings.Keys){
 if($key.StartsWith('GIMP3_')){New-Item -ItemType Directory -Path $settings[$key] -Force | Out-Null}
 $previous[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
 [Environment]::SetEnvironmentVariable($key,$settings[$key],'Process')
}
Push-Location $projectRoot
try {
 $started=Get-Date
 $batchCode="exec(open('scripts/gimp/build_approved_eye_motion.py',encoding='utf-8').read()); exec(open('scripts/gimp/build_approved_eye_import_kit.py',encoding='utf-8').read()); exec(open('scripts/gimp/inspect_approved_eye_continuity.py',encoding='utf-8').read())"
 if(-not(Test-Path -LiteralPath 'assets/private/ciel/live2d/gimp/cubism-eye-material-v5/semantic-hair-parts.psd')){
  $batchCode="exec(open('scripts/gimp/build_cubism_hair_material.py',encoding='utf-8').read()); "+$batchCode
 }
 & $gimp --new-instance --no-data --no-fonts --no-splash --console-messages --batch-interpreter=python-fu-eval --batch $batchCode --quit
 if($LASTEXITCODE -ne 0){throw 'GIMP build failed.'}
 $output=Join-Path $projectRoot 'assets/private/ciel/live2d/gimp/approved-eye-motion-v1'
 $reportFile=Get-Item -LiteralPath (Join-Path $output 'verification.json')
 $report=Get-Content -LiteralPath $reportFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
 if($reportFile.LastWriteTime -lt $started -or -not $report.expression_atlas.neutral_equal -or $report.expression_atlas.blink_levels -ne 33){throw 'Missing fresh, verified atlas.'}
 foreach($name in @('materials-report','import-kit-report','continuity-report')){
  if((Get-Item -LiteralPath (Join-Path $output "$name.json")).LastWriteTime -lt $started){throw "Missing fresh $name."}
 }
 if($Publish){
  $public=Join-Path $projectRoot 'docs/assets/ciel/production'
  foreach($name in @('comparison','combined-comparison','blink-atlas','mouth-atlas')){
   Copy-Item -LiteralPath (Join-Path $output "$name.png") -Destination (Join-Path $public "ciel-approved-eye-motion-v1-$name.png")
  }
  Copy-Item -LiteralPath $reportFile.FullName -Destination (Join-Path $public 'ciel-approved-eye-motion-v1-report.json')
  Copy-Item -LiteralPath (Join-Path $output 'materials-report.json') -Destination (Join-Path $public 'ciel-approved-eye-motion-v1-materials-report.json')
  foreach($name in @('import-kit-report.json','continuity-report.json','continuity-comparison.png')){
   Copy-Item -LiteralPath (Join-Path $output $name) -Destination (Join-Path $public "ciel-approved-eye-motion-v1-$name")
  }
 }
} finally {
 Pop-Location
 foreach($key in $previous.Keys){[Environment]::SetEnvironmentVariable($key,$previous[$key],'Process')}
}
