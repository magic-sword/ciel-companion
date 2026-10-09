$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
public static class PorcelainTransfer {
 static double Clamp(double v,double a,double b){return Math.Max(a,Math.Min(b,v));}
 static byte Byte(double v){return (byte)Math.Round(Clamp(v,0,255));}
 public static double[] Sample(string file,int x,int y,int w,int h){
  using(var im=new Bitmap(file)){double[] s=new double[3];for(int yy=y;yy<y+h;yy++)for(int xx=x;xx<x+w;xx++){var c=im.GetPixel(xx,yy);s[0]+=c.R;s[1]+=c.G;s[2]+=c.B;}for(int i=0;i<3;i++)s[i]/=w*h;return s;}
 }
 public static long[] Apply(string source,string destination,string mode,double[] lit,double[] shadow){
  using(var original=new Bitmap(source))using(var im=original.Clone(new Rectangle(0,0,original.Width,original.Height),PixelFormat.Format32bppArgb)){
   int w=im.Width,h=im.Height;var d=im.LockBits(new Rectangle(0,0,w,h),ImageLockMode.ReadWrite,PixelFormat.Format32bppArgb);
   byte[] p=new byte[d.Stride*h];Marshal.Copy(d.Scan0,p,0,p.Length);long changed=0,visible=0;
   for(int y=0;y<h;y++)for(int x=0;x<w;x++){
    int k=y*d.Stride+x*4;if(p[k+3]==0)continue;visible++;
    double b=p[k],g=p[k+1],r=p[k+2],mask=0;
    if(mode=="overlay"){
     // Retain the original alpha and spatial falloff. Only mute the warm pigment.
     double gray=(r+g+b)/3;
     p[k+2]=Byte(gray+0.20*(r-gray));p[k+1]=Byte(gray+0.20*(g-gray));p[k]=Byte(gray+0.20*(b-gray));
    }else{
     if(mode=="skin")mask=Clamp((Math.Max(r,Math.Max(g,b))-160)/35,0,1);
     else{
      // Warm pale material only. Cool hair, cyan eyes, collar and dark linework are excluded.
      mask=Clamp((r-g-0.5)/2,0,1)*Clamp((r-b+1)/3,0,1)*Clamp((r-175)/25,0,1);
      if(Math.Max(r,Math.Max(g,b))-Math.Min(r,Math.Min(g,b))>65)mask=0;
     }
     if(mask==0)continue;
     double rr=r;
     // Featureless C bases were uniformly too dark/yellow; lift only their light surface.
     if(mode=="skin")rr+=5*Clamp((r-220)/25,0,1);
     rr=Math.Min(rr,lit[0]);
     double t=Clamp((lit[0]-rr)/(lit[0]-shadow[0]),0,1);
     double rg=(lit[0]-lit[1])*(1-t)+(shadow[0]-shadow[1])*t;
     double rb=(lit[0]-lit[2])*(1-t)+(shadow[0]-shadow[2])*t;
     p[k+2]=Byte(r+(rr-r)*mask);p[k+1]=Byte(g+(rr-rg-g)*mask);p[k]=Byte(b+(rr-rb-b)*mask);
    }
    if(p[k]!=b || p[k+1]!=g || p[k+2]!=r)changed++;
   }
   Marshal.Copy(p,0,d.Scan0,p.Length);im.UnlockBits(d);im.Save(destination,ImageFormat.Png);
   return new long[]{w,h,visible,changed};
  }
 }
 public static long[] Verify(string source,string destination){
  using(var a=new Bitmap(source))using(var b=new Bitmap(destination)){
   if(a.Size!=b.Size)throw new Exception("Dimensions changed");long alpha=0,cool=0;
   for(int y=0;y<a.Height;y++)for(int x=0;x<a.Width;x++){
    var p=a.GetPixel(x,y);var q=b.GetPixel(x,y);if(p.A!=q.A)alpha++;
    if(p.A>0 && (p.B>p.R+2 || Math.Max(p.R,Math.Max(p.G,p.B))<160) && p.ToArgb()!=q.ToArgb())cool++;
   }return new long[]{alpha,cool};
  }
 }
}
'@
$root = Split-Path -Parent $PSScriptRoot
$base = Join-Path $root 'assets/ciel/generated'
$review = Join-Path $base 'skin-review'
New-Item -ItemType Directory -Force $review | Out-Null
$reference = Join-Path $base 'upper-body-1x.png'
$lit = [PorcelainTransfer]::Sample($reference,500,590,80,25)
$shadow = [PorcelainTransfer]::Sample($reference,520,695,70,10)
$jobs = @()
foreach($dir in @('pose-ref','edits')) {
 foreach($f in Get-ChildItem (Join-Path $base $dir) -Filter '*.png' | Where-Object BaseName -NotLike '*_porcelain'){
  $jobs += @{source=$f.FullName;output=(Join-Path $f.DirectoryName ($f.BaseName+'_porcelain.png'));mode='selective'}
 }
}
$f=Get-Item (Join-Path $base 'normal/face_base_neck.png')
$jobs+=@{source=$f.FullName;output=(Join-Path $f.DirectoryName ($f.BaseName+'_porcelain.png'));mode='selective'}
foreach($f in Get-ChildItem (Join-Path $base 'parts/underlayers') -Filter '*_v2.png' | Where-Object Name -Match '^(C-|K-|N-)'){
 $mode='selective';if($f.Name -like 'C-*'){$mode='skin'};if($f.Name -like 'N-*'){$mode='overlay'}
 $jobs+=@{source=$f.FullName;output=($f.FullName -replace '_v2.png$','_v3.png');mode=$mode}
}
$entries=@()
foreach($job in $jobs){
 $stats=[PorcelainTransfer]::Apply($job.source,$job.output,$job.mode,$lit,$shadow)
 $check=[PorcelainTransfer]::Verify($job.source,$job.output)
 if($check[0] -ne 0){throw "Alpha changed: $($job.output)"}
 if($job.mode -eq 'selective' -and $check[1] -ne 0){throw "Protected colors changed: $($job.output)"}
 $entries += [ordered]@{source=$job.source.Substring($base.Length+1).Replace('\','/');file=$job.output.Substring($base.Length+1).Replace('\','/');mode=$job.mode;width=$stats[0];height=$stats[1];visible_pixels=$stats[2];changed_pixels=$stats[3];alpha_differences=$check[0];protected_color_differences=$check[1]}
 Write-Output ($entries[-1].file+' : '+$stats[3]+' pixels; alpha unchanged')
}
[ordered]@{reference='upper-body-1x.png';light_sample=@{rect=@(500,590,80,25);rgb=$lit};shadow_sample=@{rect=@(520,695,70,10);rgb=$shadow};method='Image-generation color study followed by selective reference-palette transfer; original geometry and alpha retained. RGB samples are sRGB image values, not calibrated physical material measurements.';images=$entries} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $review 'manifest.json') -Encoding UTF8
