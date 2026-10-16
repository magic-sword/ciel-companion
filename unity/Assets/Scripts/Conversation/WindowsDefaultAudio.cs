// Windows：OS の設定で「既定」になっているマイク・スピーカーの ID を調べる（Core Audio の IMMDeviceEnumerator）。
// LiveKit の端末の音声（WebRTC）は、機器の ID に空を渡すと「一覧の最初の機器」を使い、OS の既定を使わない。
// 一覧の順は起動のたびに変わることがあるので、「既定」を選んだときは、ここで調べた ID をそのまま渡す。
// 返す ID は IMMDevice.GetId の文字列（"{0.0.0.00000000}.{…}"）で、WebRTC の機器の GUID と同じ形。Windows 以外では null。
using System;
using System.Runtime.InteropServices;

namespace Ciel.Conversation
{
    public static class WindowsDefaultAudio
    {
        public static string Speaker() => Get(0);   // eRender
        public static string Mic() => Get(1);       // eCapture

#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
        static string Get(int dataFlow)
        {
            IMMDeviceEnumerator enumerator = null;
            IMMDevice device = null;
            try
            {
                enumerator = (IMMDeviceEnumerator)new MMDeviceEnumerator();
                // eConsole（0）：Windows のサウンドの設定で「既定のデバイス」になっている機器
                if (enumerator.GetDefaultAudioEndpoint(dataFlow, 0, out device) != 0 || device == null) return null;
                return device.GetId(out var id) == 0 ? id : null;
            }
            catch (Exception) { return null; }   // 機器が 1 つもないときなど
            finally
            {
                if (device != null) Marshal.ReleaseComObject(device);
                if (enumerator != null) Marshal.ReleaseComObject(enumerator);
            }
        }

        [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
        class MMDeviceEnumerator { }

        [ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDeviceEnumerator
        {
            int EnumAudioEndpoints(int dataFlow, int stateMask, out IntPtr devices);
            int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
        }

        [ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IMMDevice
        {
            int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, out IntPtr instance);
            int OpenPropertyStore(int access, out IntPtr properties);
            int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
            int GetState(out int state);
        }
#else
        static string Get(int dataFlow) => null;
#endif
    }
}
