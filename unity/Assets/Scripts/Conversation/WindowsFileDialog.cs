// Windows の「ファイルを開く」ダイアログ（comdlg32 の GetOpenFileNameW）。シエルに画像を見せるときに使う（CielConversation.Image.cs）。
// Unity には実行時のファイルの選び方が無いので、Windows の API を直接呼ぶ。Windows 以外では使えない（Available が false）。
using System;
using System.Runtime.InteropServices;

namespace Ciel.Conversation
{
    static class WindowsFileDialog
    {
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
        public static bool Available => true;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct OpenFileName
        {
            public int lStructSize;
            public IntPtr hwndOwner;
            public IntPtr hInstance;
            public string lpstrFilter;
            public string lpstrCustomFilter;
            public int nMaxCustFilter;
            public int nFilterIndex;
            public IntPtr lpstrFile;
            public int nMaxFile;
            public string lpstrFileTitle;
            public int nMaxFileTitle;
            public string lpstrInitialDir;
            public string lpstrTitle;
            public int Flags;
            public short nFileOffset;
            public short nFileExtension;
            public string lpstrDefExt;
            public IntPtr lCustData;
            public IntPtr lpfnHook;
            public string lpTemplateName;
            public IntPtr pvReserved;
            public int dwReserved;
            public int FlagsEx;
        }

        [DllImport("comdlg32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern bool GetOpenFileNameW(ref OpenFileName ofn);

        [DllImport("user32.dll")]
        static extern IntPtr GetActiveWindow();

        const int OFN_FILEMUSTEXIST = 0x1000, OFN_PATHMUSTEXIST = 0x800, OFN_NOCHANGEDIR = 0x8, OFN_EXPLORER = 0x80000;
        const int MaxPath = 4096;

        /// 画像を 1 つ選ぶ。取り消したら null。選んでいるあいだは、アプリの描画が止まる（ダイアログが閉じるまで戻らない）
        public static string PickImage(string title)
        {
            var buffer = Marshal.AllocHGlobal(MaxPath * 2);
            try
            {
                Marshal.WriteInt16(buffer, 0);
                var ofn = new OpenFileName
                {
                    lStructSize = Marshal.SizeOf<OpenFileName>(),
                    hwndOwner = GetActiveWindow(),
                    lpstrFilter = "画像（*.png;*.jpg;*.jpeg）\0*.png;*.jpg;*.jpeg\0\0",
                    lpstrFile = buffer,
                    nMaxFile = MaxPath,
                    lpstrTitle = title,
                    Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER,
                };
                return GetOpenFileNameW(ref ofn) ? Marshal.PtrToStringUni(buffer) : null;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
#else
        public static bool Available => false;
        public static string PickImage(string title) => null;
#endif
    }
}
