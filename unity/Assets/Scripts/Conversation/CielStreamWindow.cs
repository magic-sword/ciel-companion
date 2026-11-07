// PC（Windows）だけ：配信用のウィンドウ「CIEL Companion 配信」。シエルと背景だけを、ボタンや文字なしで映す。
// OBS のウィンドウキャプチャでこのウィンドウを取り込めば、設定・参加者の名前・操作のボタンは映らない（操作はいままでのアプリのウィンドウで）。
// Unity のアプリは画面を 1 つしか持てない（ほかのモニターへ出す Display は、モニターが 2 台ないと開けない）ので、
// Windows の普通のウィンドウをここで作り、シエルを映すもう 1 台のカメラの絵（RenderTexture）を毎フレーム写す。
// 絵は GPU から読み出して（AsyncGPUReadback）、GDI（StretchDIBits）でウィンドウに描く。アプリの画面より 1 フレームほど遅れる。
// GDI で描くので、OBS の「ゲームキャプチャ」（プロセスの Direct3D の画面を横取りする）では取り込めない。ゲームキャプチャは
// このウィンドウを選んでも同じプロセスの Unity の画面（アプリのウィンドウ）を映す（2026-11-07）。「ウィンドウキャプチャ」で取り込む。
// 絵の大きさはウィンドウの中の大きさに合わせる（大きさは自由に変えられる。次に開くときも同じ大きさ）。
// ウィンドウを閉じると、設定（PlayerPrefs）も切る。ビルドしたアプリでは最初から開く。エディタでは設定で開く。
// 配信の背景（Backdrop）：アプリと同じ絵か、一色（グリーンバック・ブルーバック）。一色のときは背景の板（CielBackground.Layer）を映さず、
// その色で塗ってからシエルを描く。OBS ではウィンドウキャプチャに「クロマキー」のフィルタを付けて色を抜く。
// ウィンドウキャプチャは透明（アルファ）を取り込めないので、透過はクロマキーで作る。
using System;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ciel.Conversation
{
    public sealed class CielStreamWindow : MonoBehaviour
    {
        public const string Title = "CIEL Broadcast 映像";
        const string ClassName = "CielStreamWindow";
        const string PrefKey = "ciel.streamWindow";
        const string WidthKey = "ciel.streamWindow.width", HeightKey = "ciel.streamWindow.height";
        const int MaxSide = 2160;   // 絵の長い辺の上限（4K の縦）

        public static bool Supported =>
            Application.platform == RuntimePlatform.WindowsPlayer || Application.platform == RuntimePlatform.WindowsEditor;

        public bool IsOpen => _hwnd != IntPtr.Zero;
        /// 配信用のカメラにだけ映す物の層（いまの目的の札。CielConversationUI.Goal.cs）。アプリのカメラは映さない
        public const int OverlayLayer = 31;
        /// 配信用のカメラ（開いていなければ null）
        public Camera StreamCamera => _hwnd != IntPtr.Zero ? _camera : null;
        public event Action Changed;

        /// 配信の背景。並びは設定画面の選ぶ順
        public enum Backdrop { App, Green, Blue }
        public static readonly string[] BackdropLabels = { "アプリと同じ", "グリーンバック", "ブルーバック" };
        const string BackdropKey = "ciel.streamWindow.backdrop";
        public Backdrop CurrentBackdrop { get; private set; }

        public void SetBackdrop(Backdrop b)
        {
            CurrentBackdrop = b;
            PlayerPrefs.SetInt(BackdropKey, (int)b);
            PlayerPrefs.Save();
            Changed?.Invoke();
        }

        static Color BackdropColor(Backdrop b) => b == Backdrop.Blue ? new Color(0f, 0f, 1f, 1f) : new Color(0f, 1f, 0f, 1f);

        static CielStreamWindow _instance;   // ウィンドウの知らせ（WndProc）から見る

        CielBackground _background;
        Camera _main, _camera;
        RenderTexture _rt;
        IntPtr _hwnd;
        byte[] _pixels;
        int _pixelsW, _pixelsH;
        bool _reading, _closeRequested;

        void Start()
        {
            _background = FindAnyObjectByType<CielBackground>();
            CurrentBackdrop = (Backdrop)Mathf.Clamp(PlayerPrefs.GetInt(BackdropKey, 0), 0, BackdropLabels.Length - 1);
            var autoOpen = !Application.isEditor && CielAppComposition.Profile != null && CielAppComposition.Profile.openOutputOnStart;
            if (Supported && PlayerPrefs.GetInt(PrefKey, autoOpen ? 1 : 0) == 1) Open();
        }

        void OnDisable() => Close();

        public void SetOpen(bool open)
        {
            PlayerPrefs.SetInt(PrefKey, open ? 1 : 0);
            if (open) Open();
            else Close();
            Changed?.Invoke();
        }

        void Open()
        {
            if (!Supported || _hwnd != IntPtr.Zero) return;
            _main = Camera.main;
            if (_main == null) return;
            _hwnd = CreateNativeWindow(PlayerPrefs.GetInt(WidthKey, 540), PlayerPrefs.GetInt(HeightKey, 960));
            if (_hwnd == IntPtr.Zero)
            {
                Debug.LogWarning($"[CielStreamWindow] 配信用のウィンドウを開けなかった（エラー {Marshal.GetLastWin32Error()}）");
                return;
            }
            _instance = this;
            // アプリのカメラの子に、同じ設定のカメラを置く（位置・向き・背景の板はアプリのカメラについて動く）
            var go = new GameObject("StreamCamera");
            go.transform.SetParent(_main.transform, false);
            _camera = go.AddComponent<Camera>();
            _camera.CopyFrom(_main);
            go.tag = "Untagged";   // Camera.main（タッチ・背景が使う）はアプリのカメラのまま
            _camera.depth = _main.depth - 1;
            _main.cullingMask &= ~(1 << OverlayLayer);     // 配信用の札は、アプリのウィンドウには映さない
            _camera.cullingMask |= 1 << OverlayLayer;
            Debug.Log($"[CielStreamWindow] 配信用のウィンドウ「{Title}」を開いた");
        }

        void Close()
        {
            if (_hwnd == IntPtr.Zero) return;
            if (!IsIconic(_hwnd) && GetClientRect(_hwnd, out var rc) && rc.Right > 0 && rc.Bottom > 0)
            {
                PlayerPrefs.SetInt(WidthKey, rc.Right);
                PlayerPrefs.SetInt(HeightKey, rc.Bottom);
            }
            DestroyWindow(_hwnd);
            UnregisterClassW(ClassName, GetModuleHandleW(null));
            _hwnd = IntPtr.Zero;
            if (_instance == this) _instance = null;
            if (_camera != null) Destroy(_camera.gameObject);
            _camera = null;
            if (_rt != null) { _rt.Release(); Destroy(_rt); }
            _rt = null;
            _pixels = null;
            if (_background != null) _background.CoverAspect = 0;
        }

        void LateUpdate()
        {
            if (_hwnd == IntPtr.Zero) return;
            if (_closeRequested || !IsWindow(_hwnd))
            {
                _closeRequested = false;
                SetOpen(false);
                return;
            }
            var minimized = IsIconic(_hwnd);
            _camera.enabled = !minimized;
            if (minimized || !GetClientRect(_hwnd, out var rc)) return;
            var (w, h) = (rc.Right, rc.Bottom);
            if (w < 2 || h < 2) return;
            var shrink = Mathf.Min(1f, (float)MaxSide / Mathf.Max(w, h));
            w = Mathf.Max(2, Mathf.RoundToInt(w * shrink));
            h = Mathf.Max(2, Mathf.RoundToInt(h * shrink));
            if (_rt == null || _rt.width != w || _rt.height != h) Resize(w, h);

            // アプリのカメラの寄り（縦の映る範囲）に合わせる。横の範囲はウィンドウの形で決まる
            _camera.orthographic = _main.orthographic;
            _camera.orthographicSize = _main.orthographicSize;
            _camera.fieldOfView = _main.fieldOfView;
            // 背景：アプリと同じ絵か、一色（背景の板の層を映さず、その色で塗る）
            var plain = CurrentBackdrop != Backdrop.App;
            _camera.clearFlags = plain ? CameraClearFlags.SolidColor : _main.clearFlags;
            _camera.backgroundColor = plain ? BackdropColor(CurrentBackdrop) : _main.backgroundColor;
            if (plain) _camera.cullingMask &= ~(1 << CielBackground.Layer);
            else _camera.cullingMask |= _main.cullingMask & (1 << CielBackground.Layer);
            if (_background != null) _background.CoverAspect = plain ? 0 : (float)w / h;   // 配信用のほうが横長でも、背景が足りるように

            // 読み出しは 1 つずつ（前のが終わってから）。ここで頼むと、前のフレームの絵が読める
            if (!_reading)
            {
                _reading = true;
                AsyncGPUReadback.Request(_rt, 0, TextureFormat.BGRA32, OnRead);
            }
        }

        void Resize(int w, int h)
        {
            _camera.targetTexture = null;
            if (_rt != null) { _rt.Release(); Destroy(_rt); }
            _rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32) { name = "CielStream" };
            _rt.Create();
            _camera.targetTexture = _rt;
            _camera.aspect = (float)w / h;
        }

        void OnRead(AsyncGPUReadbackRequest request)
        {
            _reading = false;
            if (this == null || _hwnd == IntPtr.Zero || request.hasError) return;
            var data = request.GetData<byte>();
            if (_pixels == null || _pixels.Length != data.Length) _pixels = new byte[data.Length];
            data.CopyTo(_pixels);
            (_pixelsW, _pixelsH) = (request.width, request.height);
            var dc = GetDC(_hwnd);
            if (dc == IntPtr.Zero) return;
            Paint(dc);
            ReleaseDC(_hwnd, dc);
        }

        // 最後に読み出した絵を、ウィンドウの中いっぱいに描く（大きさを変えている途中は引き伸ばす）
        void Paint(IntPtr dc)
        {
            if (_pixels == null || !GetClientRect(_hwnd, out var rc)) return;
            var header = new BITMAPINFOHEADER
            {
                biSize = (uint)Marshal.SizeOf<BITMAPINFOHEADER>(),
                biWidth = _pixelsW,
                biHeight = _pixelsH,   // 正の値＝下の行から（Unity の絵の並びと同じ）
                biPlanes = 1,
                biBitCount = 32,
            };
            var same = rc.Right == _pixelsW && rc.Bottom == _pixelsH;
            SetStretchBltMode(dc, same ? COLORONCOLOR : HALFTONE);
            StretchDIBits(dc, 0, 0, rc.Right, rc.Bottom, 0, 0, _pixelsW, _pixelsH, _pixels, ref header, DIB_RGB_COLORS, SRCCOPY);
        }

        // ---- Windows のウィンドウ ----

        static readonly WndProcDelegate Proc = WndProc;   // 関数の場所を Windows に渡すので、消されないように持っておく

        static IntPtr CreateNativeWindow(int width, int height)
        {
            var module = GetModuleHandleW(null);
            UnregisterClassW(ClassName, module);   // エディタでスクリプトを読み込み直す前の登録（古い WndProc を指す）が残っていれば消す
            var wc = new WNDCLASSEX
            {
                cbSize = (uint)Marshal.SizeOf<WNDCLASSEX>(),
                style = CS_HREDRAW | CS_VREDRAW,
                lpfnWndProc = Marshal.GetFunctionPointerForDelegate(Proc),
                hInstance = module,
                hCursor = LoadCursorW(IntPtr.Zero, (IntPtr)IDC_ARROW),
                hbrBackground = GetStockObject(BLACK_BRUSH),
                lpszClassName = ClassName,
            };
            if (RegisterClassExW(ref wc) == 0) return IntPtr.Zero;
            var rect = new RECT { Right = Mathf.Max(width, 160), Bottom = Mathf.Max(height, 160) };
            AdjustWindowRectEx(ref rect, WS_OVERLAPPEDWINDOW, false, 0);
            var hwnd = CreateWindowExW(0, ClassName, Title, WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
                rect.Right - rect.Left, rect.Bottom - rect.Top, IntPtr.Zero, IntPtr.Zero, module, IntPtr.Zero);
            if (hwnd != IntPtr.Zero) ShowWindow(hwnd, SW_SHOWNOACTIVATE);   // アプリのウィンドウから前面を奪わない
            return hwnd;
        }

        // ウィンドウへの知らせ。Unity のメインのスレッドで、Unity がメッセージを配るときに呼ばれる
        [AOT.MonoPInvokeCallback(typeof(WndProcDelegate))]
        static IntPtr WndProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam)
        {
            try
            {
                var self = _instance != null && _instance._hwnd == hWnd ? _instance : null;
                switch (msg)
                {
                    case WM_CLOSE:   // 閉じるのは次のフレームで（設定も切る）
                        if (self != null) self._closeRequested = true;
                        return IntPtr.Zero;
                    case WM_ERASEBKGND:   // 絵があるときは黒で塗らない（大きさを変えるときにちらつく）
                        if (self != null && self._pixels != null) return (IntPtr)1;
                        break;
                    case WM_PAINT:
                        var dc = BeginPaint(hWnd, out var ps);
                        if (self != null) self.Paint(dc);
                        EndPaint(hWnd, ref ps);
                        return IntPtr.Zero;
                }
            }
            catch (Exception e) { Debug.LogException(e); }
            return DefWindowProcW(hWnd, msg, wParam, lParam);
        }

        delegate IntPtr WndProcDelegate(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

        const uint WM_PAINT = 0x000F, WM_CLOSE = 0x0010, WM_ERASEBKGND = 0x0014;
        const uint WS_OVERLAPPEDWINDOW = 0x00CF0000, CS_VREDRAW = 0x0001, CS_HREDRAW = 0x0002;
        const int CW_USEDEFAULT = unchecked((int)0x80000000), SW_SHOWNOACTIVATE = 4, IDC_ARROW = 32512, BLACK_BRUSH = 4;
        const int COLORONCOLOR = 3, HALFTONE = 4;
        const uint DIB_RGB_COLORS = 0, SRCCOPY = 0x00CC0020;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct WNDCLASSEX
        {
            public uint cbSize, style;
            public IntPtr lpfnWndProc;
            public int cbClsExtra, cbWndExtra;
            public IntPtr hInstance, hIcon, hCursor, hbrBackground;
            public string lpszMenuName, lpszClassName;
            public IntPtr hIconSm;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct RECT { public int Left, Top, Right, Bottom; }

        [StructLayout(LayoutKind.Sequential)]
        struct PAINTSTRUCT
        {
            public IntPtr hdc;
            public int fErase;
            public RECT rcPaint;
            public int fRestore, fIncUpdate;
            [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)] public byte[] rgbReserved;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct BITMAPINFOHEADER
        {
            public uint biSize;
            public int biWidth, biHeight;
            public ushort biPlanes, biBitCount;
            public uint biCompression, biSizeImage;
            public int biXPelsPerMeter, biYPelsPerMeter;
            public uint biClrUsed, biClrImportant;
        }

        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] static extern ushort RegisterClassExW(ref WNDCLASSEX wc);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern bool UnregisterClassW(string className, IntPtr instance);
        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CreateWindowExW(uint exStyle, string className, string windowName, uint style,
            int x, int y, int width, int height, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr param);
        [DllImport("user32.dll")] static extern bool DestroyWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int cmd);
        [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr hWnd, out RECT rect);
        [DllImport("user32.dll")] static extern bool AdjustWindowRectEx(ref RECT rect, uint style, bool menu, uint exStyle);
        [DllImport("user32.dll")] static extern IntPtr DefWindowProcW(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")] static extern IntPtr LoadCursorW(IntPtr instance, IntPtr name);
        [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr hWnd);
        [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr hWnd, IntPtr dc);
        [DllImport("user32.dll")] static extern IntPtr BeginPaint(IntPtr hWnd, out PAINTSTRUCT ps);
        [DllImport("user32.dll")] static extern bool EndPaint(IntPtr hWnd, ref PAINTSTRUCT ps);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr GetModuleHandleW(string name);
        [DllImport("gdi32.dll")] static extern IntPtr GetStockObject(int index);
        [DllImport("gdi32.dll")] static extern int SetStretchBltMode(IntPtr dc, int mode);
        [DllImport("gdi32.dll")]
        static extern int StretchDIBits(IntPtr dc, int xDest, int yDest, int wDest, int hDest, int xSrc, int ySrc, int wSrc, int hSrc,
            byte[] bits, ref BITMAPINFOHEADER info, uint usage, uint rop);
    }
}
