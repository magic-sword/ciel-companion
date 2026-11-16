// 会話（CielConversation）のうち、家の中だけの試験用サーバーにつなぐ（docs/operations/local-livekit-ja.md）。
// 自宅サーバーで scripts/server/livekit-local.sh start を動かしているときだけ使う。クラウドの LiveKit を使わず、
// 家の中の LiveKit と試験用の会話サーバーで話す。トークンは家の中の窓口（token_server.py）から受け取る。
// 取得先の URL は設定画面で入れ、PlayerPrefs の ciel.localServerUrl に覚える（例：http://<自宅サーバー>:7883/token）。
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string LocalServerPrefKey = "ciel.localServer";
        const string LocalServerUrlPrefKey = "ciel.localServerUrl";

        /// 家の中の試験用サーバーにつなぐか（設定画面の開発の欄）
        public bool LocalServer { get; private set; }
        /// 家の中の試験用サーバーのトークンの取得先
        public string LocalServerUrl { get; private set; } = "";

        void LoadLocalServer()
        {
            LocalServerUrl = PlayerPrefs.GetString(LocalServerUrlPrefKey, "");
            LocalServer = PlayerPrefs.GetInt(LocalServerPrefKey, 0) == 1 && LocalServerUrl != "";
        }

        public void SetLocalServer(bool on)
        {
            on = on && LocalServerUrl != "";
            if (on == LocalServer) return;
            LocalServer = on;
            PlayerPrefs.SetInt(LocalServerPrefKey, on ? 1 : 0);
            PlayerPrefs.Save();
            ReconnectForServer();
            Changed?.Invoke();
        }

        public void SetLocalServerUrl(string url)
        {
            url = (url ?? "").Trim();
            if (url == LocalServerUrl) return;
            LocalServerUrl = url;
            PlayerPrefs.SetString(LocalServerUrlPrefKey, url);
            PlayerPrefs.Save();
            if (url == "" && LocalServer) SetLocalServer(false);
            else if (LocalServer) ReconnectForServer();
            Changed?.Invoke();
        }

        // 会話は別のサーバーになるので、つないでいたらつなぎ直す（開発スイッチと同じ）
        void ReconnectForServer()
        {
            if (Status == State.Connected || Status == State.Failed)
            {
                EndConversation();
                StartConversation();
            }
            else if (Status == State.Connecting) _restartAfterConnect = true;
        }
    }
}
