<#
.SYNOPSIS
  素材v2の基準画像から、目のレイヤー（白目・虹彩・まつ毛・二重の線）を作る。

.DESCRIPTION
  入力（prepare-ciel-source-v2.ps1 の出力）:
    master/ciel-upper-body-2x.png          通常の顔
    master/ciel-upper-body-2x-eyeless.png  同じ画像から両目を消したもの（依頼B）。目のない顔の肌として使う
    master/ciel-upper-body-2x-eyes-closed.png  瞬きの瞬間（依頼C）。閉じたまつ毛と二重の線を取り出す
  2枚の差から目の範囲を求め、色で分類してレイヤーにする。
  - まつ毛・二重の線: 目のない画像を背景として透明度と色を逆算
  - 虹彩: 色の付いた画素の凸包。まつ毛の下に隠れる上部は見えている虹彩から補完
  - 白目: 目の範囲。虹彩とまつ毛の下に隠れる部分は見えている白目から補完
  出力: layers/eyes/{R,L}_{sclera,iris,lash,crease}.png（基準画像と同じ2172×2896）、
        layers/eyes/check-{R,L}.png（元画像・重ね直し・差×3）、layers/eyes/report.json
  重ね順は 目のない顔 < 白目 < 虹彩 < まつ毛 < 二重の線。L/R はキャラクターから見た左右（R＝画面左）。
#>
param(
  [string]$SourceRoot = (Join-Path $PSScriptRoot '..\assets\private\ciel\live2d\source-v2')
)
$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path $SourceRoot).Path
$outDir = Join-Path $SourceRoot 'layers\eyes'
[IO.Directory]::CreateDirectory($outDir) | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition ([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'lib\CielLayers.cs')))

# Region of interest per eye, and the iris centre/radii from the bounding box of strongly blue pixels
# (the ellipse is only used for the part of the iris hidden under the lash).
$eyes = @(
  @{ side='R'; x=730;  y=900; w=340; h=260; icx=921;  icy=1057; rx=67.5; ry=69.5 }
  @{ side='L'; x=1150; y=890; w=340; h=260; icx=1288; icy=1044; rx=67.5; ry=69.5 }
)
$m = [Layer]::Load((Join-Path $SourceRoot 'master\ciel-upper-body-2x.png'))
$b = [Layer]::Load((Join-Path $SourceRoot 'master\ciel-upper-body-2x-eyeless.png'))
$names = 'sclera','iris','lash','crease'
$report = [ordered]@{ generatedBy = 'scripts/build-ciel-eye-layers.ps1'; order = 'eyeless < sclera < iris < lash < crease'; eyes = @() }
foreach ($e in $eyes) {
  $mc = $m.Crop($e.x, $e.y, $e.w, $e.h); $bc = $b.Crop($e.x, $e.y, $e.w, $e.h)
  $r = [EyeSep]::Run($mc, $bc, $e.icx - $e.x, $e.icy - $e.y, $e.rx, $e.ry)
  for ($i = 0; $i -lt 4; $i++) {
    [Layer]::Paste($r[$i], $m.W, $m.H, $e.x, $e.y).Save((Join-Path $outDir ('{0}_{1}.png' -f $e.side, $names[$i])))
  }
  $comp = $bc.Clone(); foreach ($i in 0..3) { $comp.Over($r[$i]) }
  $rms = [Layer]::Rms($comp, $mc)
  $report.eyes += [ordered]@{ side = $e.side; roi = @($e.x, $e.y, $e.w, $e.h); recompositeRms = [math]::Round($rms, 2); closedRecompositeRms = $null }
  [Layer]::HCat($mc, $comp, [Layer]::Diff($comp, $mc, 3)).Scale(2).Save((Join-Path $outDir "check-$($e.side).png"))
}
# Closed eyes (request C, the blink illustration): only the closed lash and the crease above it are used.
$k = [Layer]::Load((Join-Path $SourceRoot 'master\ciel-upper-body-2x-eyes-closed.png'))
foreach ($e in $eyes) {
  $kc = $k.Crop($e.x, $e.y, $e.w, $e.h); $bc = $b.Crop($e.x, $e.y, $e.w, $e.h)
  $r = [EyeSep]::Closed($kc, $bc)
  [Layer]::Paste($r[0], $m.W, $m.H, $e.x, $e.y).Save((Join-Path $outDir "$($e.side)_lash_closed.png"))
  [Layer]::Paste($r[1], $m.W, $m.H, $e.x, $e.y).Save((Join-Path $outDir "$($e.side)_crease_closed.png"))
  $comp = $bc.Clone(); $comp.Over($r[0]); $comp.Over($r[1])
  $rms = [Layer]::Rms($comp, $kc)
  ($report.eyes | Where-Object { $_.side -eq $e.side }).closedRecompositeRms = [math]::Round($rms, 2)
  [Layer]::HCat($kc, $comp, [Layer]::Diff($comp, $kc, 3)).Scale(2).Save((Join-Path $outDir "check-$($e.side)-closed.png"))
}
# Half-open eyes (the half-blink illustration): all four layers are separated the same way as the open eyes,
# so the half-open pose keeps the iris shape and only the lid covers it. Output: {R,L}_{sclera,iris,lash,crease}_half.png
$h = [Layer]::Load((Join-Path $SourceRoot 'master\ciel-upper-body-2x-eyes-half.png'))
foreach ($e in $eyes) {
  $hc = $h.Crop($e.x, $e.y, $e.w, $e.h); $bc = $b.Crop($e.x, $e.y, $e.w, $e.h)
  $r = [EyeSep]::Run($hc, $bc, $e.icx - $e.x, $e.icy - $e.y, $e.rx, $e.ry)
  for ($i = 0; $i -lt 4; $i++) {
    [Layer]::Paste($r[$i], $m.W, $m.H, $e.x, $e.y).Save((Join-Path $outDir ('{0}_{1}_half.png' -f $e.side, $names[$i])))
  }
  $comp = $bc.Clone(); foreach ($i in 0..3) { $comp.Over($r[$i]) }
  $rms = [Layer]::Rms($comp, $hc)
  $item = $report.eyes | Where-Object { $_.side -eq $e.side }
  $item['halfRecompositeRms'] = [math]::Round($rms, 2)
  [Layer]::HCat($hc, $comp, [Layer]::Diff($comp, $hc, 3)).Scale(2).Save((Join-Path $outDir "check-$($e.side)-half.png"))
}
$report | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 (Join-Path $outDir 'report.json')
Write-Output ('EYE_LAYERS_READY ' + (($report.eyes | ForEach-Object { "$($_.side) rms=$($_.recompositeRms) closed=$($_.closedRecompositeRms)" }) -join ' '))
