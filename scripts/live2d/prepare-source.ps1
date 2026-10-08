<#
.SYNOPSIS
  Live2D素材v2の入力を整える。生成画像は変更せず、master/ と normalized/ を再生成する。

.DESCRIPTION
  - master: 透過付きの等倍上半身と、黒背景の2倍アップスケール(JPEG)から、透過付きの2倍上半身を作る。
    透明度は等倍画像のアルファを2倍に補間し、色は黒背景との合成を逆算して求める。
  - normalized: 生成パーツをキャラから見た左右(L/R)の英数字名へ統一し、ほぼ不透明(>=248)の画素を255にする。
  - manifest.json: 元ファイル名・キャンバスサイズ・描画範囲・用途を記録する。
  入力は assets/ciel/generated/（Git管理）、出力の master/ normalized/ manifest.json は assets/ciel/ 内の Git 除外フォルダ（再生成できる）。
#>
param(
  [string]$SourceRoot = (Join-Path $PSScriptRoot '..\..\assets\ciel')
)
$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path $SourceRoot).Path
$gen = Join-Path $SourceRoot 'generated'
$masterDir = Join-Path $SourceRoot 'master'
$normDir = Join-Path $SourceRoot 'normalized'

Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing @'
using System; using System.Drawing; using System.Drawing.Imaging; using System.Runtime.InteropServices;
public static class CielPx {
  public static byte[] Read(Bitmap b) {
    var d = b.LockBits(new Rectangle(0,0,b.Width,b.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
    var buf = new byte[b.Width*b.Height*4];
    for (int y=0;y<b.Height;y++) Marshal.Copy(d.Scan0 + y*d.Stride, buf, y*b.Width*4, b.Width*4);
    b.UnlockBits(d); return buf;
  }
  public static Bitmap Write(byte[] buf, int w, int h) {
    var b = new Bitmap(w, h, PixelFormat.Format32bppArgb);
    var d = b.LockBits(new Rectangle(0,0,w,h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
    for (int y=0;y<h;y++) Marshal.Copy(buf, y*w*4, d.Scan0 + y*d.Stride, w*4);
    b.UnlockBits(d); return b;
  }
  // Bicubic resize of a single 8-bit channel (no premultiplication side effects).
  public static byte[] ResizeChannel(byte[] src, int sw, int sh, int ch, int dw, int dh) {
    var o = new byte[dw*dh];
    double fx = (double)sw/dw, fy = (double)sh/dh;
    for (int y=0;y<dh;y++) {
      double sy = (y+0.5)*fy-0.5; int iy=(int)Math.Floor(sy); double ty=sy-iy;
      for (int x=0;x<dw;x++) {
        double sx = (x+0.5)*fx-0.5; int ix=(int)Math.Floor(sx); double tx=sx-ix; double v=0;
        for (int m=-1;m<=2;m++) { int yy=Math.Min(sh-1,Math.Max(0,iy+m)); double wy=K(m-ty);
          for (int n=-1;n<=2;n++) { int xx=Math.Min(sw-1,Math.Max(0,ix+n)); v += src[(yy*sw+xx)*4+ch]*wy*K(n-tx); } }
        o[y*dw+x] = (byte)Math.Max(0,Math.Min(255,Math.Round(v)));
      }
    }
    return o;
  }
  static double K(double t) { t=Math.Abs(t); const double a=-0.5;
    if (t<=1) return (a+2)*t*t*t-(a+3)*t*t+1; if (t<2) return a*t*t*t-5*a*t*t+8*a*t-4*a; return 0; }
  public static void SnapOpaque(byte[] px, int threshold) {
    for (int i=3;i<px.Length;i+=4) if (px[i]>=threshold) px[i]=255;
  }
  // big: upscaled image flattened on black. small: original with alpha. Returns BGRA at big size.
  public static byte[] Unflatten(byte[] big, int bw, int bh, byte[] small, int sw, int sh) {
    var a = ResizeChannel(small, sw, sh, 3, bw, bh);
    // Fallback colour for faint edges: upsampled original colour weighted by alpha.
    var pre = new byte[small.Length];
    for (int i=0;i<small.Length;i+=4){ double al=small[i+3]/255.0; for(int k=0;k<3;k++) pre[i+k]=(byte)Math.Round(small[i+k]*al); pre[i+3]=small[i+3]; }
    var fb = new byte[3][]; for (int k=0;k<3;k++) fb[k]=ResizeChannel(pre, sw, sh, k, bw, bh);
    var o = new byte[bw*bh*4];
    for (int p=0;p<bw*bh;p++) {
      int al=a[p]; o[p*4+3]=(byte)al; if (al==0) continue;
      for (int k=0;k<3;k++) {
        double obs = big[p*4+k];
        double fromBig = obs*255.0/al;
        double fromSmall = fb[k][p]*255.0/al;
        double t = Math.Min(1.0, Math.Max(0.0, (al-32)/96.0));   // faint edges lean on the original, solid areas on the upscale
        o[p*4+k] = (byte)Math.Max(0, Math.Min(255, Math.Round(fromBig*t + fromSmall*(1-t))));
      }
    }
    return o;
  }
  // Paste an edited crop (cand, no alpha) into the master: master(x,y) <- cand((x-ox)/s, (y-oy)/s), area-averaged,
  // blended in over `feather` px from the crop border. The master alpha is kept.
  public static void PasteEdit(byte[] m, int mw, int mh, byte[] c, int cw, int ch, double s, double sy, double ox, double oy, int feather) {
    int x0=(int)Math.Ceiling(ox), y0=(int)Math.Ceiling(oy), x1=(int)Math.Floor(ox+cw*s)-1, y1=(int)Math.Floor(oy+ch*sy)-1;
    const int SS=4;
    for (int y=Math.Max(0,y0); y<=Math.Min(mh-1,y1); y++) for (int x=Math.Max(0,x0); x<=Math.Min(mw-1,x1); x++) {
      double d=Math.Min(Math.Min(x-x0+1, x1-x+1), Math.Min(y-y0+1, y1-y+1));
      double w=Math.Min(1.0, d/feather); if (w<=0) continue;
      double[] acc=new double[3];
      for (int j=0;j<SS;j++) for (int i=0;i<SS;i++) {
        double px=(x+(i+0.5)/SS-ox)/s-0.5, py=(y+(j+0.5)/SS-oy)/sy-0.5;
        int ix=(int)Math.Floor(px), iy=(int)Math.Floor(py); double fx=px-ix, fy=py-iy;
        for (int k=0;k<3;k++) {
          double v=0;
          for (int b=0;b<2;b++) for (int a=0;a<2;a++) { int xx=Math.Min(cw-1,Math.Max(0,ix+a)), yy=Math.Min(ch-1,Math.Max(0,iy+b));
            v+=c[(yy*cw+xx)*4+k]*(a==0?1-fx:fx)*(b==0?1-fy:fy); }
          acc[k]+=v/(SS*SS);
        }
      }
      int p=(y*mw+x)*4;
      for (int k=0;k<3;k++) m[p+k]=(byte)Math.Max(0,Math.Min(255,Math.Round(acc[k]*w + m[p+k]*(1-w))));
    }
  }
  public static int[] Bounds(byte[] px, int w, int h) {
    int x0=w,y0=h,x1=-1,y1=-1;
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) if (px[(y*w+x)*4+3]>8){ if(x<x0)x0=x; if(y<y0)y0=y; if(x>x1)x1=x; if(y>y1)y1=y; }
    return new int[]{x0,y0,x1,y1};
  }
}
'@

function Load([string]$path) {
  $b = [System.Drawing.Bitmap]::FromFile($path)
  try { return @{ W = $b.Width; H = $b.Height; Px = [CielPx]::Read($b) } } finally { $b.Dispose() }
}
function Save($img, [string]$path) {
  $b = [CielPx]::Write($img.Px, $img.W, $img.H)
  try { $b.Save($path, [System.Drawing.Imaging.ImageFormat]::Png) } finally { $b.Dispose() }
}
function Hash([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLower() }

New-Item -ItemType Directory -Force $masterDir, $normDir, (Join-Path $normDir 'normal'), (Join-Path $normDir 'expression') | Out-Null

# --- master ---
$smallPath = Join-Path $gen 'upper-body-1x.png'
$bigPath = Join-Path $gen 'upper-body-2x-firefly-black.jpg'
$small = Load $smallPath
$big = Load $bigPath
if ($big.W -ne $small.W*2 -or $big.H -ne $small.H*2) { throw "Upscale must be exactly 2x: $($big.W)x$($big.H)" }
[CielPx]::SnapOpaque($small.Px, 248)
Save $small (Join-Path $masterDir 'ciel-upper-body-1x.png')
$master = @{ W = $big.W; H = $big.H; Px = [CielPx]::Unflatten($big.Px, $big.W, $big.H, $small.Px, $small.W, $small.H) }
Save $master (Join-Path $masterDir 'ciel-upper-body-2x-base.png')

# --- accepted edits (made on requests/face-crop-1024x576_x598_y762.png, then upscaled by the editing tool) ---
# scale/offset map the edited image back onto the master; measured by registration (residual outside the edit: RMS 1.3).
$edits = @(
  [ordered]@{ file = 'edit-a-eye-strands-removed.png'; what = '目にかかる毛束を消し、前髪の毛束を目の上で止めた'; scale = 0.7031; ox = 598.0; oy = 762.0; feather = 16 }
)
foreach ($e in $edits) {
  $path = Join-Path $gen $e.file
  $c = Load $path
  [CielPx]::PasteEdit($master.Px, $master.W, $master.H, $c.Px, $c.W, $c.H, $e.scale, $e.scale, $e.ox, $e.oy, $e.feather)
  $e.sourceSha256 = Hash $path
}
Save $master (Join-Path $masterDir 'ciel-upper-body-2x.png')

# --- stage images: same canvas as the master, one more thing removed each (used to separate layers by difference) ---
$stages = @(
  [ordered]@{ file = 'edit-b-eyes-removed.png'; out = 'ciel-upper-body-2x-eyeless.png'; what = '両目（まつ毛・二重の線を含む）を消して肌にした（Aの編集結果を元に作成）'; scale = 0.7030; ox = 597.9; oy = 762.0; feather = 16 }
  [ordered]@{ file = 'edit-c-eyes-closed.png'; out = 'ciel-upper-body-2x-eyes-closed.png'; what = '両目を閉じた瞬きの瞬間。閉じたまつ毛と二重の線だけを使う（範囲外の差 RMS 3.6〜5.7、縦横の倍率がわずかに異なる）'; scale = 0.6116; scaleY = 0.6095; ox = 598.2; oy = 762.4; feather = 16 }
  [ordered]@{ file = 'ciel-face-half-blink-1024x576.png'; out = 'ciel-upper-body-2x-eyes-half.png'; what = '半目（上まぶたが降りたジト目）。切り抜き 1024x576 と同じ大きさ・位置（倍率1.0、オフセット(598,762)）。目の4レイヤーを取り出す'; scale = 1.0; ox = 598.0; oy = 762.0; feather = 16 }
)
foreach ($st in $stages) {
  $path = Join-Path $gen $st.file
  $c = Load $path
  $stage = @{ W = $master.W; H = $master.H; Px = [byte[]]$master.Px.Clone() }
  $sy = if ($st.Contains('scaleY')) { $st.scaleY } else { $st.scale }
  [CielPx]::PasteEdit($stage.Px, $stage.W, $stage.H, $c.Px, $c.W, $c.H, $st.scale, $sy, $st.ox, $st.oy, $st.feather)
  Save $stage (Join-Path $masterDir $st.out)
  $st.sourceSha256 = Hash $path
}

# --- normalized parts: same relative names as generated/ (L/R = character's own left/right; the right eye is on the viewer's left) ---
# 元の日本語ファイル名は generated/original-names.json に記録。L_iris_duplicate.png は L_iris.png と同一のため対象外。
$parts = [ordered]@{
  'normal\face_base_neck.png'          = '目・前髪の下に隠れる肌（素顔下地）'
  'normal\mouth_closed.png'            = '閉じた口'
  'normal\R_sclera.png'                = '右目 白目'
  'normal\L_sclera.png'                = '左目 白目'
  'normal\R_iris.png'                  = '右目 虹彩'
  'normal\L_iris.png'                  = '左目 虹彩'
  'normal\R_lashes_open.png'           = '右目 上まつ毛・下まぶた線'
  'normal\L_lashes_open.png'           = '左目 上まつ毛・下まぶた線'
  'normal\R_brow.png'                  = '右眉'
  'normal\L_brow.png'                  = '左眉（別キャンバス）'
  'expression\mouth_open.png'          = '開いた口（口パク）'
  'expression\R_lashes_closed.png'     = '右目 閉眼まつ毛'
  'expression\L_lashes_closed.png'     = '左目 閉眼まつ毛'
}

$records = @()
foreach ($name in $parts.Keys) {
  $srcPath = Join-Path $gen $name
  $img = Load $srcPath
  [CielPx]::SnapOpaque($img.Px, 248)
  Save $img (Join-Path $normDir $name)
  $bb = [CielPx]::Bounds($img.Px, $img.W, $img.H)
  $records += [ordered]@{
    file = $name.Replace('\', '/'); use = $parts[$name]
    canvas = @($img.W, $img.H); bounds = @($bb[0], $bb[1], $bb[2], $bb[3]); sourceSha256 = (Hash $srcPath)
  }
}

$manifest = [ordered]@{
  generatedBy = 'scripts/live2d/prepare-source.ps1'
  convention = 'L/R はキャラクターから見た左右。キャラの右目は画面の左側。'
  note = '生成パーツは基準画像と同じ絵ではない。基準画像の位置・大きさへ合わせてから、隠れる部分と差分にだけ使う。'
  master = [ordered]@{
    file = 'master/ciel-upper-body-2x.png'; size = @($master.W, $master.H)
    alphaFrom = 'generated/upper-body-1x.png'; colourFrom = 'generated/upper-body-2x-firefly-black.jpg（黒背景の合成を逆算）'
    sources = [ordered]@{ small = (Hash $smallPath); upscale = (Hash $bigPath) }
    base = 'master/ciel-upper-body-2x-base.png（部分修正を適用する前）'
    edits = $edits
    stages = $stages
  }
  parts = $records
}
$manifest | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $SourceRoot 'manifest.json')
Write-Output "SOURCE_V2_READY master=$($master.W)x$($master.H) parts=$($records.Count)"
