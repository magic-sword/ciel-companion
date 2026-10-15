// Android で、シエルの声を本体のスピーカーから出すか、受話口（耳に当てるスピーカー）から出すかを切り替える。
// LiveKit（WebRTC）は会話を通話として扱い、Android は既定で受話口から鳴らす。切り替えは OS の AudioManager が行うので、
// アプリから頼む（LiveKit の PlatformAudio の説明のとおり）。Android 12（API 31）以降は setCommunicationDevice、
// それより前は setSpeakerphoneOn。Android 以外では何もしない。
using UnityEngine;

namespace Ciel.Conversation
{
    public static class AndroidSpeaker
    {
        const int TypeBuiltinSpeaker = 2;   // AudioDeviceInfo.TYPE_BUILTIN_SPEAKER

        /// 切り替えられたら true
        public static bool Set(bool speaker)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using var player = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
                using var activity = player.GetStatic<AndroidJavaObject>("currentActivity");
                using var audio = activity.Call<AndroidJavaObject>("getSystemService", "audio");
                using var version = new AndroidJavaClass("android.os.Build$VERSION");
                if (version.GetStatic<int>("SDK_INT") >= 31)
                {
                    if (!speaker)
                    {
                        audio.Call("clearCommunicationDevice");
                        return true;
                    }
                    using var devices = audio.Call<AndroidJavaObject>("getAvailableCommunicationDevices");
                    int n = devices.Call<int>("size");
                    for (int i = 0; i < n; i++)
                    {
                        using var d = devices.Call<AndroidJavaObject>("get", i);
                        if (d.Call<int>("getType") == TypeBuiltinSpeaker)
                            return audio.Call<bool>("setCommunicationDevice", d);
                    }
                    Debug.LogWarning("[AndroidSpeaker] 本体のスピーカーが見つからない");
                    return false;
                }
                audio.Call("setSpeakerphoneOn", speaker);
                return true;
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[AndroidSpeaker] 切り替えられない: {e.Message}");
                return false;
            }
#else
            return false;
#endif
        }
    }
}
