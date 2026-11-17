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
        public const string DefaultLocalServerUrl = "http://192.168.1.15:7883/token";

        /// 家の中の試験用サーバーにつなぐか（設定画面の開発の欄）
        public bool LocalServer { get; private set; }
        /// 家の中の試験用サーバーのトークンの取得先
        public string LocalServerUrl { get; private set; } = DefaultLocalServerUrl;

        static string LocalTokenEndpoint(string url) => string.IsNullOrWhiteSpace(url)
            ? DefaultLocalServerUrl : url.Trim();

        void LoadLocalServer()
        {
            LocalServerUrl = LocalTokenEndpoint(PlayerPrefs.GetString(LocalServerUrlPrefKey, ""));
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
            url = LocalTokenEndpoint(url);
            if (url == LocalServerUrl) return;
            LocalServerUrl = url;
            PlayerPrefs.SetString(LocalServerUrlPrefKey, url);
            PlayerPrefs.Save();
            if (LocalServer) ReconnectForServer();
            Changed?.Invoke();
        }

        // 家の中の窓口からトークンを受け取る。Unity の通信（UnityWebRequest）は http を許さない設定なので、
        // この取得先だけ .NET の HttpClient で送る（ほかの通信の設定は変えない）。失敗したら null を返す
        static System.Collections.IEnumerator FetchLocalToken(string url, string body, System.Action<string> done)
        {
            using var http = new System.Net.Http.HttpClient { Timeout = System.TimeSpan.FromSeconds(10) };
            var send = http.PostAsync(url, new System.Net.Http.StringContent(body, System.Text.Encoding.UTF8, "application/json"));
            while (!send.IsCompleted) yield return null;
            if (send.IsFaulted || send.IsCanceled || !send.Result.IsSuccessStatusCode)
            {
                Debug.LogError($"[CielConversation] 家の中の窓口に届かない: {send.Exception?.GetBaseException().Message ?? send.Result?.StatusCode.ToString()}");
                done(null);
                yield break;
            }
            var read = send.Result.Content.ReadAsStringAsync();
            while (!read.IsCompleted) yield return null;
            done(read.IsFaulted ? null : read.Result);
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
