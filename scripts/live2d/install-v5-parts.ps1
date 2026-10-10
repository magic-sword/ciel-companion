<#
.SYNOPSIS
  v5 のパーツ（assets/ciel/generated/v5/parts）を、正式なレイヤーの置き場所 assets/ciel/layers/{head,body} に置く。
.DESCRIPTION
  同じ名前の古いレイヤーは上書きする。v5 で使わなくなった古いレイヤー（Hair_Under_Ear・Face_Base など）と、
  古い後処理の退避ファイル（*.orig.png・*.prechin.png・*.pre-a2.png）は削除する。
  目（layers/eyes）・口（Mouth_*）・犬耳（Ear_L/R）は既存のまま使う。
#>
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$src = Join-Path $root 'assets/ciel/generated/v5/parts'
$layers = Join-Path $root 'assets/ciel/layers'
$head = 'Hair_Back', 'Face_Skin', 'Face_Blush', 'Face_Nose', 'Hair_Crown', 'Hair_Side_L', 'Hair_Side_R', 'Hair_Front', 'Brow_L', 'Brow_R', 'Hair_Ahoge'
$body = 'Body_Base', 'Outer_L', 'Outer_R', 'Body_Fur', 'Waist_Belt', 'Chest_Gem', 'Neck_Gear'
foreach ($n in $head) { Copy-Item (Join-Path $src "$n.png") (Join-Path $layers "head/$n.png") -Force }
foreach ($n in $body) { Copy-Item (Join-Path $src "$n.png") (Join-Path $layers "body/$n.png") -Force }
$obsolete = 'head/Hair_Under_Ear.png', 'head/Face_Base.png'
foreach ($o in $obsolete) { $p = Join-Path $layers $o; if (Test-Path $p) { Remove-Item $p } }
Get-ChildItem $layers -Recurse -File | Where-Object { $_.Name -match '\.(orig|prechin|pre-a2|chin-k)\.png$' } | Remove-Item
# v5 のパーツの後処理（顎の線を別レイヤーへ、首の上側を明るく）
$py = 'C:\Users\prog\anaconda3\python.exe'
& $py -I (Join-Path $PSScriptRoot 'split-jaw-line.py')
& $py -I (Join-Path $PSScriptRoot 'lighten-neck.py')
Write-Output 'V5_PARTS_INSTALLED'
