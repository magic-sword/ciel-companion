$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$out = Join-Path $root 'assets/ciel/generated/v22'
$selection = Get-Content (Join-Path $out 'selection.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$size = 480; $gap = 24; $labelHeight = 78; $header = 120
$width = 4*$size + 5*$gap
$height = $header + 3*($size+$labelHeight+$gap) + 58
$sheet = [Drawing.Bitmap]::new($width,$height)
$g = [Drawing.Graphics]::FromImage($sheet)
$g.Clear([Drawing.Color]::FromArgb(246,248,252))
$g.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$titleFont = [Drawing.Font]::new('Yu Gothic',28,[Drawing.FontStyle]::Bold)
$labelFont = [Drawing.Font]::new('Yu Gothic',20,[Drawing.FontStyle]::Bold)
$smallFont = [Drawing.Font]::new('Yu Gothic',12)
$ink = [Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(38,55,76))
$subInk = [Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(84,101,121))
$tile = [Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(220,227,238))
$g.DrawString('シエル 表情見本 v22',$titleFont,$ink,24,20)
$g.DrawString('確認用・暫定候補 ／ 元絵との微差と採用回は report.md を参照',$smallFont,$subInk,28,76)
$index = 0
foreach ($row in $selection) {
    $name = $row.name
    $dest = Join-Path $out "expressions/$name.png"
    if ($name -eq 'neutral') {
        Copy-Item (Join-Path $out 'inputs/approved-face-ears.png') $dest -Force
    } else {
        $key = '{0}-{1:00}' -f $name,[int]$row.attempt
        Copy-Item (Join-Path $out "qa/$key-normalized.png") $dest -Force
    }
    $im = [Drawing.Image]::FromFile($dest)
    if ($im.Width -ne 1664 -or $im.Height -ne 1664) { throw "Wrong size: $name" }
    $x = $gap + ($index % 4)*($size+$gap)
    $y = $header + [math]::Floor($index/4)*($size+$labelHeight+$gap)
    $g.FillRectangle($tile,$x,$y,$size,$size)
    $g.DrawImage($im,[int]$x,[int]$y,$size,$size)
    $g.DrawString([string]$row.label,$labelFont,$ink,[single]($x+12),[single]($y+$size+7))
    $g.DrawString($name,$smallFont,$subInk,[single]($x+14),[single]($y+$size+44))
    $im.Dispose(); $index++
}
if ($index -ne 12) { throw 'Exactly 12 expressions are required.' }
$g.DrawString('表情の目標を検討するための見本です。Live2D 用のパーツ素材ではありません。',$smallFont,$subInk,28,($height-45))
$sheet.Save((Join-Path $out 'expressions-sheet.png'),[Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $sheet.Dispose()
$titleFont.Dispose(); $labelFont.Dispose(); $smallFont.Dispose(); $ink.Dispose(); $subInk.Dispose(); $tile.Dispose()
Write-Output "Saved 12 portraits (1664x1664) and sheet ($($width)x$($height))."
