// Layer toolkit and eye separation for the CIEL Live2D source v2. Loaded by scripts/build-ciel-eye-layers.ps1.
// Layer pixels are BGRA with straight alpha.
using System; using System.Collections.Generic; using System.Drawing; using System.Drawing.Imaging; using System.Runtime.InteropServices;
public class Layer {
  public int W, H; public byte[] P; // BGRA straight alpha
  public Layer(int w, int h) { W=w; H=h; P=new byte[w*h*4]; }
  public static Layer Load(string path) {
    using (var b = new Bitmap(path)) {
      var l = new Layer(b.Width, b.Height);
      var d = b.LockBits(new Rectangle(0,0,b.Width,b.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
      for (int y=0;y<b.Height;y++) Marshal.Copy(d.Scan0 + y*d.Stride, l.P, y*b.Width*4, b.Width*4);
      b.UnlockBits(d); return l;
    }
  }
  public void Save(string path) {
    using (var b = new Bitmap(W, H, PixelFormat.Format32bppArgb)) {
      var d = b.LockBits(new Rectangle(0,0,W,H), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
      for (int y=0;y<H;y++) Marshal.Copy(P, y*W*4, d.Scan0 + y*d.Stride, W*4);
      b.UnlockBits(d); b.Save(path, ImageFormat.Png);
    }
  }
  public Layer Clone() { var l = new Layer(W,H); Buffer.BlockCopy(P,0,l.P,0,P.Length); return l; }
  // Place src scaled by (kx,ky) so that src (ax,ay) lands on (mx,my). Optional rotation in degrees about the anchor.
  public static Layer Place(Layer src, int w, int h, double kx, double ky, double ax, double ay, double mx, double my, double rotDeg) {
    var o = new Layer(w,h); double c=Math.Cos(rotDeg*Math.PI/180), s=Math.Sin(rotDeg*Math.PI/180);
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) {
      double dx=x+0.5-mx, dy=y+0.5-my; double rx= c*dx + s*dy, ry= -s*dx + c*dy;
      double sx = rx/kx + ax - 0.5, sy = ry/ky + ay - 0.5;
      if (sx < -1 || sy < -1 || sx > src.W || sy > src.H) continue;
      int x0=(int)Math.Floor(sx), y0=(int)Math.Floor(sy); double fx=sx-x0, fy=sy-y0;
      double a=0, r=0, g=0, b=0;
      for (int j=0;j<2;j++) for (int i=0;i<2;i++) {
        int xx=x0+i, yy=y0+j; if (xx<0||yy<0||xx>=src.W||yy>=src.H) continue;
        double wgt=(i==0?1-fx:fx)*(j==0?1-fy:fy); int k=(yy*src.W+xx)*4; double al=src.P[k+3]/255.0*wgt;
        a+=al; b+=src.P[k]*al; g+=src.P[k+1]*al; r+=src.P[k+2]*al;
      }
      if (a<=0) continue; int q=(y*w+x)*4;
      o.P[q]=(byte)Math.Round(b/a); o.P[q+1]=(byte)Math.Round(g/a); o.P[q+2]=(byte)Math.Round(r/a); o.P[q+3]=(byte)Math.Round(Math.Min(1,a)*255);
    }
    return o;
  }
  // Source-over composite of top onto this (in place).
  public void Over(Layer t) {
    for (int i=0;i<P.Length;i+=4) {
      double ta=t.P[i+3]/255.0; if (ta<=0) continue; double ba=P[i+3]/255.0; double oa=ta+ba*(1-ta);
      for (int k=0;k<3;k++) P[i+k]=(byte)Math.Round((t.P[i+k]*ta + P[i+k]*ba*(1-ta))/oa);
      P[i+3]=(byte)Math.Round(oa*255);
    }
  }
  public static Layer Solid(int w, int h, byte r, byte g, byte b) { var l=new Layer(w,h); for(int i=0;i<l.P.Length;i+=4){l.P[i]=b;l.P[i+1]=g;l.P[i+2]=r;l.P[i+3]=255;} return l; }
  public Layer Crop(int x, int y, int w, int h) { var o=new Layer(w,h); for(int j=0;j<h;j++) for(int i=0;i<w;i++){ int sx=x+i, sy=y+j; if(sx<0||sy<0||sx>=W||sy>=H) continue; Buffer.BlockCopy(P,(sy*W+sx)*4,o.P,(j*w+i)*4,4);} return o; }
  public Layer Scale(int f) { var o=new Layer(W*f,H*f); for(int y=0;y<o.H;y++) for(int x=0;x<o.W;x++) Buffer.BlockCopy(P,((y/f)*W+x/f)*4,o.P,(y*o.W+x)*4,4); return o; }
  public static Layer Paste(Layer s, int w, int h, int x, int y) { var o=new Layer(w,h); for(int j=0;j<s.H;j++){ int yy=y+j; if(yy<0||yy>=h) continue; for(int i=0;i<s.W;i++){ int xx=x+i; if(xx<0||xx>=w) continue; Buffer.BlockCopy(s.P,(j*s.W+i)*4,o.P,(yy*w+xx)*4,4);} } return o; }
  public static double Rms(Layer a, Layer b) { double e=0; long n=0; for(int i=0;i<a.P.Length;i+=4) for(int k=0;k<3;k++){ double d=a.P[i+k]-b.P[i+k]; e+=d*d; n++; } return Math.Sqrt(e/n); }
  public static Layer Diff(Layer a, Layer b, int gain) { var o=new Layer(a.W,a.H); for(int i=0;i<a.P.Length;i+=4){ int v=0; for(int k=0;k<3;k++) v=Math.Max(v,Math.Abs(a.P[i+k]-b.P[i+k])); v=Math.Min(255,v*gain); o.P[i]=o.P[i+1]=o.P[i+2]=(byte)v; o.P[i+3]=255; } return o; }
  public static Layer HCat(params Layer[] ls) { int w=0,h=0; foreach(var l in ls){w+=l.W+6; h=Math.Max(h,l.H);} var o=Solid(w,h,40,45,60); int ox=0; foreach(var l in ls){ for(int y=0;y<l.H;y++) Buffer.BlockCopy(l.P,y*l.W*4,o.P,(y*w+ox)*4,l.W*4); ox+=l.W+6;} return o; }
}
public static class EyeSep {
  static double L(byte[] p, int i) { return (p[i]+p[i+1]+p[i+2])/3.0; }
  static double D(byte[] a, byte[] b, int i) { return Math.Max(Math.Abs(a[i]-b[i]), Math.Max(Math.Abs(a[i+1]-b[i+1]), Math.Abs(a[i+2]-b[i+2]))); }
  // Flood fill from ROI border over pixels where mask==false; returns true for pixels NOT reached (holes filled).
  static bool[] FillHoles(bool[] m, int w, int h) {
    var outside = new bool[w*h]; var q = new Queue<int>();
    for (int x=0;x<w;x++){ q.Enqueue(x); q.Enqueue((h-1)*w+x); } for (int y=0;y<h;y++){ q.Enqueue(y*w); q.Enqueue(y*w+w-1); }
    while (q.Count>0) { int i=q.Dequeue(); if (i<0||i>=w*h||outside[i]||m[i]) continue; outside[i]=true; int x=i%w;
      if (x>0) q.Enqueue(i-1); if (x<w-1) q.Enqueue(i+1); q.Enqueue(i-w); q.Enqueue(i+w); }
    var o = new bool[w*h]; for (int i=0;i<w*h;i++) o[i]=!outside[i]; return o;
  }
  static bool[] Morph(bool[] m, int w, int h, int r, bool dilate) {
    var o=new bool[w*h];
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) { bool v = !dilate;
      for (int j=-r;j<=r && v!=dilate;j++) for (int i=-r;i<=r;i++) { if (i*i+j*j>r*r) continue; int xx=x+i, yy=y+j;
        bool s = (xx>=0&&yy>=0&&xx<w&&yy<h) ? m[yy*w+xx] : false; if (dilate && s) { v=true; break; } if (!dilate && !s) { v=false; break; } }
      o[y*w+x]=v; }
    return o;
  }
  static bool[] KeepLarge(bool[] m, int w, int h, int minArea) {
    var lab=new int[w*h]; var o=new bool[w*h]; int id=0;
    for (int s=0;s<w*h;s++) { if (!m[s]||lab[s]!=0) continue; id++; var list=new List<int>(); var q=new Queue<int>(); q.Enqueue(s); lab[s]=id;
      while(q.Count>0){ int i=q.Dequeue(); list.Add(i); int x=i%w; foreach (int j in new[]{i-1,i+1,i-w,i+w}) { if (j<0||j>=w*h) continue; if ((j==i-1&&x==0)||(j==i+1&&x==w-1)) continue; if (m[j]&&lab[j]==0){lab[j]=id;q.Enqueue(j);} } }
      if (list.Count>=minArea) foreach (int i in list) o[i]=true; }
    return o;
  }
  static void Diffuse(Layer l, bool[] known, bool[] domain, int iters) {
    int w=l.W, h=l.H; var c=new double[w*h*3]; var has=(bool[])known.Clone();
    for (int i=0;i<w*h;i++) for (int k=0;k<3;k++) c[i*3+k]=l.P[i*4+k];
    for (int pass=0;pass<2000;pass++) { bool ch=false; var nh=(bool[])has.Clone();
      for (int y=1;y<h-1;y++) for (int x=1;x<w-1;x++) { int i=y*w+x; if (has[i]||!domain[i]) continue; double s0=0,s1=0,s2=0; int n=0;
        foreach (int j in new[]{i-1,i+1,i-w,i+w}) if (has[j]) { s0+=c[j*3]; s1+=c[j*3+1]; s2+=c[j*3+2]; n++; }
        if (n>0) { c[i*3]=s0/n; c[i*3+1]=s1/n; c[i*3+2]=s2/n; nh[i]=true; ch=true; } }
      has=nh; if (!ch) break; }
    for (int it=0;it<iters;it++) for (int y=1;y<h-1;y++) for (int x=1;x<w-1;x++) { int i=y*w+x; if (known[i]||!domain[i]||!has[i]) continue;
      double s0=0,s1=0,s2=0; int n=0; foreach (int j in new[]{i-1,i+1,i-w,i+w}) if (has[j]&&domain[j]) { s0+=c[j*3]; s1+=c[j*3+1]; s2+=c[j*3+2]; n++; }
      if (n>0) { c[i*3]=s0/n; c[i*3+1]=s1/n; c[i*3+2]=s2/n; } }
    for (int i=0;i<w*h;i++) if (domain[i]&&!known[i]&&has[i]) for (int k=0;k<3;k++) l.P[i*4+k]=(byte)Math.Round(c[i*3+k]);
  }
  static bool[] Hull(bool[] m, int w, int h) {
    var pts=new List<long>(); for (int y=0;y<h;y++){ int a=-1,b=-1; for (int x=0;x<w;x++) if (m[y*w+x]) { if (a<0) a=x; b=x; } if (a>=0){ pts.Add(((long)a<<32)|(uint)y); pts.Add(((long)(b+1)<<32)|(uint)y); pts.Add(((long)a<<32)|(uint)(y+1)); pts.Add(((long)(b+1)<<32)|(uint)(y+1)); } }
    var P=new List<double[]>(); foreach (var p in pts) P.Add(new double[]{ (double)(p>>32), (double)(p&0xffffffff) });
    P.Sort((u,v)=> u[0]!=v[0] ? u[0].CompareTo(v[0]) : u[1].CompareTo(v[1]));
    Func<double[],double[],double[],double> cr=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
    var H=new List<double[]>();
    foreach (var p in P) { while (H.Count>=2 && cr(H[H.Count-2],H[H.Count-1],p)<=0) H.RemoveAt(H.Count-1); H.Add(p); }
    int lo=H.Count+1; for (int i=P.Count-2;i>=0;i--) { var p=P[i]; while (H.Count>=lo && cr(H[H.Count-2],H[H.Count-1],p)<=0) H.RemoveAt(H.Count-1); H.Add(p); }
    H.RemoveAt(H.Count-1);
    var o2=new bool[w*h];
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) { double px=x+0.5, py=y+0.5; bool inside=true;
      for (int i=0;i<H.Count;i++) { var a=H[i]; var b=H[(i+1)%H.Count]; if ((b[0]-a[0])*(py-a[1])-(b[1]-a[1])*(px-a[0]) < 0) { inside=false; break; } }
      o2[y*w+x]=inside; }
    return o2;
  }
  // Dark lines (lash) matted against the background: alpha from the lightness drop relative to the nearby core.
  static Layer MatteDark(Layer M, Layer B, bool[] core, bool[] zone) {
    int w=M.W, h=M.H, n=w*h; var LA=new Layer(w,h);
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) { int i=y*w+x; if (!zone[i]) continue; double mn=999;
      for (int j=-4;j<=4;j++) for (int k=-4;k<=4;k++) { int xx=x+k, yy=y+j; if (xx<0||yy<0||xx>=w||yy>=h) continue; int t=yy*w+xx; if (core[t]) mn=Math.Min(mn,L(M.P,t*4)); }
      if (mn>900) continue; int q=i*4;
      double lb=L(B.P,q), lm=L(M.P,q); double a=Math.Max(0,Math.Min(1,(lb-lm)/Math.Max(20,lb-mn)));
      if (core[i] && lm<170) a=1;
      if (a<0.03) continue;
      for (int k=0;k<3;k++) LA.P[q+k]=(byte)Math.Max(0,Math.Min(255,Math.Round((M.P[q+k]-(1-a)*B.P[q+k])/a)));
      LA.P[q+3]=(byte)Math.Round(a*255); }
    return LA;
  }
  // Closed eye: [0]=lash [1]=crease, matted against the eyeless background B.
  public static Layer[] Closed(Layer M, Layer B) {
    int w=M.W, h=M.H, n=w*h;
    var lash=new bool[n]; var crease=new bool[n];
    for (int i=0;i<n;i++) { int q=i*4; double d=D(M.P,B.P,q); int b=M.P[q], r=M.P[q+2]; double l=L(M.P,q);
      lash[i] = d>9 && l<200 && b<r+25;
      crease[i] = d>8 && l>=150 && r>b+6; }
    var core = KeepLarge(lash,w,h,150);
    var g1 = Morph(core,w,h,1,true);
    var cm = new bool[n]; for (int i=0;i<n;i++) cm[i]=crease[i] && !g1[i];
    cm = KeepLarge(cm,w,h,40);
    var LA = MatteDark(M, B, core, Morph(core,w,h,2,true));
    var CR=new Layer(w,h); var cz = Morph(cm,w,h,1,true);
    for (int i=0;i<n;i++) { if (!cz[i]) continue; int q=i*4; double d=D(M.P,B.P,q); double a=Math.Max(0,Math.Min(1,d/45.0)); if (a<0.04) continue;
      for (int k=0;k<3;k++) CR.P[q+k]=(byte)Math.Max(0,Math.Min(255,Math.Round((M.P[q+k]-(1-a)*B.P[q+k])/a)));
      CR.P[q+3]=(byte)Math.Round(a*255); }
    return new[]{LA, CR};
  }
  // Returns layers: [0]=sclera [1]=iris [2]=lash [3]=crease, all ROI-sized; plus [4]=debug silhouette
  public static Layer[] Run(Layer M, Layer B, double icx, double icy, double irx, double iry) {
    int w=M.W, h=M.H, n=w*h;
    var lash=new bool[n]; var big=new bool[n]; var crease=new bool[n];
    for (int i=0;i<n;i++) { int q=i*4; double d=D(M.P,B.P,q); int b=M.P[q], r=M.P[q+2]; double l=L(M.P,q);
      lash[i] = d>9 && l<190 && b<r+25;
      crease[i] = d>8 && l>=150 && r>b+6;
      big[i] = d>5 && !crease[i]; }
    // silhouette: closing + hole fill + keep large
    var sil = KeepLarge(FillHoles(Morph(Morph(big,w,h,3,true),w,h,3,false),w,h), w,h, 3000);
    // iris ellipse coverage
    var irisCov=new float[n];
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) { double dd=Math.Sqrt(Math.Pow((x+0.5-icx)/(irx+2),2)+Math.Pow((y+0.5-icy)/(iry+2),2)); irisCov[y*w+x]=(float)Math.Max(0,Math.Min(1,(1-dd)*(irx+iry)/2+0.5)); }
    var lashCore = new bool[n]; for (int i=0;i<n;i++) lashCore[i]=lash[i]&&sil[i];
    lashCore = KeepLarge(lashCore,w,h,200);
    var creaseM = new bool[n]; var silG = Morph(sil,w,h,3,true);
    var lashG1 = Morph(lashCore,w,h,1,true); for (int i=0;i<n;i++) creaseM[i]=crease[i] && !lashG1[i] && !sil[i];
    creaseM = KeepLarge(creaseM,w,h,40);
    // --- lash layer: matte against the eyeless background around the lash core
    var lashZone = Morph(lashCore,w,h,2,true);
    var Lr=new double[n]; for (int i=0;i<n;i++) Lr[i]=999;
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) { int i=y*w+x; if (!lashZone[i]) continue; double mn=999;
      for (int j=-4;j<=4;j++) for (int k=-4;k<=4;k++) { int xx=x+k, yy=y+j; if (xx<0||yy<0||xx>=w||yy>=h) continue; int t=yy*w+xx; if (lashCore[t]) mn=Math.Min(mn,L(M.P,t*4)); }
      Lr[i]=mn; }
    var LA=new Layer(w,h);
    for (int i=0;i<n;i++) { if (!lashZone[i]) continue; int q=i*4; if (Lr[i]>900) continue;
      double lb=L(B.P,q), lm=L(M.P,q); double a=Math.Max(0,Math.Min(1,(lb-lm)/Math.Max(20,lb-Lr[i])));
      if (lashCore[i] && L(M.P,q)<170) a=1;
      if (a<0.03) continue;
      for (int k=0;k<3;k++) LA.P[q+k]=(byte)Math.Max(0,Math.Min(255,Math.Round((M.P[q+k]-(1-a)*B.P[q+k])/a)));
      LA.P[q+3]=(byte)Math.Round(a*255); }
    // --- crease layer: matte against background
    var CR=new Layer(w,h); var creaseZ = Morph(creaseM,w,h,1,true);
    for (int i=0;i<n;i++) { if (!creaseZ[i]) continue; int q=i*4; double d=D(M.P,B.P,q); double a=Math.Max(0,Math.Min(1,d/45.0)); if (a<0.04) continue;
      for (int k=0;k<3;k++) CR.P[q+k]=(byte)Math.Max(0,Math.Min(255,Math.Round((M.P[q+k]-(1-a)*B.P[q+k])/a)));
      CR.P[q+3]=(byte)Math.Round(a*255); }
    // --- iris layer: master inside ellipse; pixels under the lash are filled from visible iris
    // visible iris = coloured (non-sclera) pixels inside the eye, holes (highlights) filled; plus the hidden part of the ellipse under the lash
    var irisVis=new bool[n];
    for (int i=0;i<n;i++) { int q=i*4; int mx=Math.Max(M.P[q],Math.Max(M.P[q+1],M.P[q+2])), mn=Math.Min(M.P[q],Math.Min(M.P[q+1],M.P[q+2]));
      bool scleraLike = L(M.P,q)>200 && (mx-mn)<45; irisVis[i] = sil[i] && !lashZone[i] && !scleraLike && (irisCov[i]>0 || M.P[q]>M.P[q+2]+10); }
    irisVis = KeepLarge(irisVis,w,h,2000); { var hu = Hull(irisVis,w,h); for (int i=0;i<n;i++) irisVis[i] = hu[i] && sil[i] && !lashZone[i]; } irisVis = Morph(irisVis,w,h,1,true);
    var IR=new Layer(w,h); var irisKnown=new bool[n]; var irisDom=new bool[n];
    for (int i=0;i<n;i++) { bool hid = irisCov[i]>0.5 && lashZone[i] && !irisVis[i]; if (!irisVis[i] && !hid) continue; int q=i*4; irisDom[i]=true;
      irisKnown[i] = irisVis[i] && !lashZone[i]; for (int k=0;k<3;k++) IR.P[q+k]=M.P[q+k]; IR.P[q+3]=255; }
    Diffuse(IR, irisKnown, irisDom, 300);
    // --- sclera layer: silhouette (grown under the lash), colours from master, hidden parts diffused
    var SC=new Layer(w,h); var scDom = Morph(sil,w,h,1,true);
    for (int x=0;x<w;x++) { int top=-1; for (int y=0;y<h;y++) if (lashCore[y*w+x]) { top=y; break; } if (top<0) continue; for (int y=0;y<top+3 && y<h;y++) scDom[y*w+x]=false; } var scKnown=new bool[n];
    var irisGrow=Morph(irisDom,w,h,2,true);
    for (int i=0;i<n;i++) { if (!scDom[i]) continue; int q=i*4; scKnown[i] = sil[i] && !lashZone[i] && !irisGrow[i] && !(M.P[q]>M.P[q+2]+25) && L(M.P,q)>185 && !crease[i];
      for (int k=0;k<3;k++) SC.P[q+k]=M.P[q+k];
      double a = sil[i] ? 1.0 : 0.5; SC.P[q+3]=(byte)Math.Round(a*255); }
    Diffuse(SC, scKnown, scDom, 400);
    var dbg=new Layer(w,h); for (int i=0;i<n;i++){ int q=i*4; dbg.P[q+3]=255; if (sil[i]) dbg.P[q+1]=180; if (lashCore[i]) dbg.P[q+2]=255; if (creaseM[i]) { dbg.P[q+2]=255; dbg.P[q+1]=220; } if (irisCov[i]>0.5) dbg.P[q]=255; }
    return new[]{SC, IR, LA, CR, dbg};
  }
}
