using UnityEngine;

namespace Ciel.Conversation
{
    [DefaultExecutionOrder(-1000)]
    public sealed class CielAppComposition : MonoBehaviour
    {
        [SerializeField] CielAppProfile _profile;
        public static CielAppProfile Profile { get; private set; }
        public static bool IsBroadcast => Profile != null && Profile.broadcast;

        void Awake()
        {
            Profile = _profile;
            if (_profile == null) { Debug.LogError("CIEL app profile is missing."); return; }
            if (!Application.isEditor && Application.platform == RuntimePlatform.WindowsPlayer)
                Screen.SetResolution(_profile.windowSize.x, _profile.windowSize.y, FullScreenMode.Windowed);
            foreach (var touch in FindObjectsByType<CielTouch>()) touch.enabled = !IsBroadcast;

            // 共通 Runtime には UI や配信出力を持たせず、ここだけが製品ごとの構成を決める。
            var shell = new GameObject(IsBroadcast ? "Broadcast Controls" : "Companion Controls");
            shell.transform.SetParent(transform, false);
            shell.SetActive(false);
            var stream = IsBroadcast && CielStreamWindow.Supported ? shell.AddComponent<CielStreamWindow>() : null;
            if (IsBroadcast && CielStreamWindow.Supported) shell.AddComponent<CielAudienceCard>();
            var ui = shell.AddComponent<CielConversationUI>();
            ui.Configure(_profile, stream);
            shell.SetActive(true);
        }

        void OnDestroy()
        {
            if (Profile == _profile) Profile = null;
        }
    }
}
