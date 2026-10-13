param([string]$Name, [int]$Attempt, [string]$Source)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$out = Join-Path $root 'assets/ciel/generated/v22'
$key = '{0}-{1:00}' -f $Name,$Attempt
$raw = Join-Path $out "attempts/$key.png"
if ($Source -ne $raw) { Copy-Item -LiteralPath $Source -Destination $raw -Force }
$reference = [Drawing.Bitmap]::FromFile((Join-Path $out 'inputs/approved-face-ears.png'))
$candidate = [Drawing.Bitmap]::FromFile($raw)
# Canvas size normalization only. No localized edits, masks, warps or paint.
$normalized = [Drawing.Bitmap]::new(1664,1664,[Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g = [Drawing.Graphics]::FromImage($normalized)
$g.CompositingMode = [Drawing.Drawing2D.CompositingMode]::SourceCopy
$g.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.PixelOffsetMode = [Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$g.DrawImage($candidate,[Drawing.Rectangle]::new(0,0,1664,1664),0,0,$candidate.Width,$candidate.Height,[Drawing.GraphicsUnit]::Pixel)
$g.Dispose()
$normalized.Save((Join-Path $out "qa/$key-normalized.png"),[Drawing.Imaging.ImageFormat]::Png)
$board = [Drawing.Bitmap]::new(1248,456)
$g = [Drawing.Graphics]::FromImage($board)
$g.Clear([Drawing.Color]::FromArgb(221,225,233))
$g.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($reference,0,40,416,416)
$g.DrawImage($normalized,416,40,416,416)
$g.DrawImage($reference,832,40,416,416)
$matrix = [Drawing.Imaging.ColorMatrix]::new()
$matrix.Matrix33 = 0.5
$attr = [Drawing.Imaging.ImageAttributes]::new()
$attr.SetColorMatrix($matrix)
$overlay = [Drawing.Bitmap]::new(1664,1664)
$og = [Drawing.Graphics]::FromImage($overlay)
$og.Clear([Drawing.Color]::FromArgb(221,225,233))
$og.DrawImageUnscaled($reference,0,0)
$og.DrawImage($normalized,[Drawing.Rectangle]::new(0,0,1664,1664),0,0,1664,1664,[Drawing.GraphicsUnit]::Pixel,$attr)
$overlay.Save((Join-Path $out "qa/$key-overlay.png"),[Drawing.Imaging.ImageFormat]::Png)
$og.Dispose(); $overlay.Dispose()
$g.DrawImage($normalized,[Drawing.Rectangle]::new(832,40,416,416),0,0,1664,1664,[Drawing.GraphicsUnit]::Pixel,$attr)
$font = [Drawing.Font]::new('Yu Gothic',15)
$g.DrawString('元絵',[Drawing.Font]$font,[Drawing.Brushes]::Black,12,5)
$g.DrawString("$key",$font,[Drawing.Brushes]::Black,428,5)
$g.DrawString('元絵 + 生成 50% 重ね合わせ',$font,[Drawing.Brushes]::Black,840,5)
$board.Save((Join-Path $out "qa/$key-compare.png"),[Drawing.Imaging.ImageFormat]::Png)
$font.Dispose(); $attr.Dispose(); $g.Dispose(); $board.Dispose()
$candidate.Dispose(); $reference.Dispose(); $normalized.Dispose()
Write-Output $key
