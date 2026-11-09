// 会話（CielConversation）のうち、アプリの道具（docs/games/game-environment-mcp-design-ja.md の 6 章）。
// アプリが出せる道具を、つないだとき・device.hello_request を受けたときに会話サーバーへ知らせる（topic ciel.app の app.hello。
// 形は MCP の tools/list と同じ）。会話サーバーの心が道具を呼ぶと app.call（id・tool・args）が届くので、名前と引数を確かめて動かし、
// app.result（id・result）で返す。知らない道具・知らない引数は動かさない（server/agent/app_env.py）。
// 道具：
//   app_gesture   シエルの体の動き（CielGesture：うなずく・首をかしげる・首を横にふる・耳をぴくっと動かす）
//   app_show_card 画面に短いカード（題と本文）を出す（CielConversationUI.Card.cs が Card を読む）
using System;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string AppTopic = "ciel.app";
        const int CardTitleChars = 20, CardBodyChars = 120;

        // 会話サーバーへ知らせる道具の一覧（MCP の tools/list の形）。説明は心がそのまま読む
        const string AppTools = "["
            + "{\"name\":\"app_gesture\",\"description\":\"シエルの体の動き（画面のシエル）。gesture は nod（うなずく）・tilt（首をかしげる）・"
            + "shake（首を横にふる）・ear（耳をぴくっと動かす）。気持ちや返事に合うときだけ、1 回の返事に 1 つまで。\","
            + "\"inputSchema\":{\"type\":\"object\",\"properties\":{\"gesture\":{\"type\":\"string\",\"enum\":[\"nod\",\"tilt\",\"shake\",\"ear\"]}},"
            + "\"required\":[\"gesture\"]},\"_meta\":{\"ciel/from_comments\":false}},"
            + "{\"name\":\"app_show_card\",\"description\":\"持ち主の画面に、短いカード（題と本文）を 12 秒ほど出す。あとで見返したいこと"
            + "（手順・材料・数・名前）を残すときに使う。title は 20 字まで、body は 120 字まで。会話をそのまま書き写さない。\","
            + "\"inputSchema\":{\"type\":\"object\",\"properties\":{\"title\":{\"type\":\"string\"},\"body\":{\"type\":\"string\"}},"
            + "\"required\":[\"title\",\"body\"]},\"_meta\":{\"ciel/from_comments\":false}}"
            + "]";

        [Serializable]
        class AppArgs
        {
            public string gesture, title, body;
        }

        [Serializable]
        class AppCall
        {
            public string type, tool;
            public int id;
            public AppArgs args;
        }

        public class CardInfo
        {
            public string Title, Body;
            public float At;
        }

        /// 画面に出すカード（app_show_card。出していなければ null）
        public CardInfo Card { get; private set; }
        /// カードが届いた回数（画面が新しいカードに気づく）
        public int CardRevision { get; private set; }

        CielGesture _gesture;

        void SendAppHello()
        {
            if (_room == null || Status != State.Connected) return;
            var json = $"{{\"v\":1,\"type\":\"app.hello\",\"app\":\"ciel-companion\",\"version\":\"{Application.version}\",\"tools\":{AppTools}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: AppTopic); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] アプリの道具を知らせられない: {e.Message}"); }
        }

        void OnAppData(byte[] data)
        {
            AppCall call;
            try { call = JsonUtility.FromJson<AppCall>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] アプリの道具の呼び出しを読めない: {ex.Message}"); return; }
            if (call == null || call.type != "app.call" || call.id <= 0) return;
            var a = call.args ?? new AppArgs();
            string result;
            switch (call.tool)
            {
                case "app_gesture":
                    var g = Gesture();
                    result = g == null ? "{\"status\":\"unavailable\"}"
                        : g.Play(a.gesture) ? "{\"status\":\"ok\"}" : "{\"status\":\"error\",\"reason\":\"unknown_gesture\"}";
                    break;
                case "app_show_card":
                    var title = Cut(a.title, CardTitleChars);
                    var body = Cut(a.body, CardBodyChars);
                    if (title == "" && body == "") { result = "{\"status\":\"error\",\"reason\":\"empty\"}"; break; }
                    Card = new CardInfo { Title = title, Body = body, At = Time.unscaledTime };
                    CardRevision++;
                    Changed?.Invoke();
                    result = "{\"status\":\"ok\"}";
                    break;
                default:
                    result = "{\"status\":\"error\",\"reason\":\"unknown_tool\"}";
                    break;
            }
            Debug.Log($"[CielConversation] アプリの道具 {call.tool}：{result}");
            var json = $"{{\"v\":1,\"type\":\"app.result\",\"id\":{call.id},\"result\":{result}}}";
            try { _room?.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: AppTopic); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] アプリの道具の結果を返せない: {e.Message}"); }
        }

        static string Cut(string s, int n)
        {
            s = (s ?? "").Trim();
            return s.Length <= n ? s : s.Substring(0, n);
        }

        /// 画面のカードを閉じる（タップ・時間切れ）
        public void CloseCard()
        {
            if (Card == null) return;
            Card = null;
            Changed?.Invoke();
        }

        // シエルのモデル（表情と同じ GameObject）に体の動きを付ける。Cubism の更新の順番に入れるため、付けたら並べ直す
        CielGesture Gesture()
        {
            if (_gesture != null) return _gesture;
            if (_expression == null) return null;
            _gesture = _expression.GetComponent<CielGesture>();
            if (_gesture == null)
            {
                _gesture = _expression.gameObject.AddComponent<CielGesture>();
                var controller = _expression.GetComponent<CubismUpdateController>();
                if (controller != null) controller.Refresh();
            }
            return _gesture;
        }
    }
}
