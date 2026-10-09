Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class UnderlayerV2 {
 public static void Clean(Bitmap im, int minSize) {
  int w=im.Width,h=im.Height;
  var d=im.LockBits(new Rectangle(0,0,w,h),ImageLockMode.ReadWrite,PixelFormat.Format32bppArgb);
  byte[] b=new byte[d.Stride*h]; Marshal.Copy(d.Scan0,b,0,b.Length);
  bool[] seen=new bool[w*h],keep=new bool[w*h]; int[] q=new int[w*h];
  for(int p=0;p<w*h;p++) {
   if(seen[p] || b[(p/w)*d.Stride+(p%w)*4+3]<24) continue;
   int head=0,tail=1; q[0]=p;seen[p]=true;
   while(head<tail) {
    int v=q[head++],x=v%w,y=v/w;
    for(int yy=Math.Max(0,y-1);yy<=Math.Min(h-1,y+1);yy++) for(int xx=Math.Max(0,x-1);xx<=Math.Min(w-1,x+1);xx++) {
     int z=yy*w+xx; if(!seen[z] && b[yy*d.Stride+xx*4+3]>=24) {seen[z]=true;q[tail++]=z;}
    }
   }
   if(tail>=minSize) for(int i=0;i<tail;i++)keep[q[i]]=true;
  }
  for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(!keep[y*w+x])b[y*d.Stride+x*4+3]=0;
  Marshal.Copy(b,0,d.Scan0,b.Length);im.UnlockBits(d);
 }
}
'@
$root = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $root 'assets/ciel/generated/parts/underlayers'
$config = Get-Content -Raw -Encoding UTF8 (Join-Path $folder 'v2-generation.json') | ConvertFrom-Json
$transforms = @{
 'C-0_face-rounded_x0_y0_v2' = @(1.35,1.177,-49.45,-7)
 'C-L30_face-rounded_xL30_y0_v2' = @(1.30,1.35,-164,-118.75)
 'C-R30_face-rounded_xR30_y0_v2' = @(1.25,1.35,-40,-72.3)
 'K-2_chin-throat_x0_yU15_v2' = @(1.10,0.683,107.3,497.995)
 'K-3_chin-throat_x0_yU30_v2' = @(1.10,1.077,80.3,117.64)
 'E-1_ear-backs_xR30_y0_v2' = @(1.20,0.90,0,-8)
}
foreach($item in $config.images) {
 $src = New-Object System.Drawing.Bitmap $item.source
 if($item.name -notlike 'N-*'){[UnderlayerV2]::Clean($src,3000)}
 $dst = New-Object System.Drawing.Bitmap 1536,1536
 $g=[System.Drawing.Graphics]::FromImage($dst)
 $g.Clear([System.Drawing.Color]::Transparent)
 $g.CompositingMode=[System.Drawing.Drawing2D.CompositingMode]::SourceCopy
 $g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
 $g.PixelOffsetMode=[System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
 if($item.name -like 'N-*') {
  $regions=@(@(370,700,195,145,440,885,180,100),@(685,700,205,145,940,885,180,100),@(600,710,55,65,765,890,35,40))
  foreach($r in $regions){
   $destRect=New-Object System.Drawing.Rectangle $r[4],$r[5],$r[6],$r[7]
   $g.DrawImage($src,$destRect,$r[0],$r[1],$r[2],$r[3],[System.Drawing.GraphicsUnit]::Pixel)
  }
 } else {
  $t=$transforms[$item.name]
  if(!$t){$t=@((1536.0/$src.Width),(1536.0/$src.Height),0,0)}
  $destRect=New-Object System.Drawing.RectangleF ([single]$t[2]),([single]$t[3]),([single]($src.Width*$t[0])),([single]($src.Height*$t[1]))
  $g.DrawImage($src,$destRect)
 }
 $g.Dispose();$src.Dispose()
 $path=Join-Path $folder ($item.name+'.png')
 $dst.Save($path,[System.Drawing.Imaging.ImageFormat]::Png);$dst.Dispose()
 Write-Output ($item.name+'.png')
}
