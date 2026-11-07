// 会話（CielConversation）のうち、YouTube の配信のコメントを受け取るか（docs/youtube-comments-design-ja.md）。
// 設定画面で配信の URL を入れてスイッチを入れると（PlayerPrefs）、つないだとき・会話サーバーが入ってきたとき・変えたときに、
// 会話サーバーへ送る（topic ciel.youtube の youtube.link。server/agent/youtube_chat.py）。コメントを読むのは会話サーバーで、
// API キーも会話サーバーが持つ（アプリはログインもキーも要らない）。どこまでつながったかは、会話サーバーが youtube.state で返す。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string YouTubeOnKey = "ciel.youtube.on", YouTubeUrlKey = "ciel.youtube.url";

        /// 配信のコメントを受け取るか・配信の URL（設定画面）
        public bool YouTube { get; private set; }
        public string YouTubeUrl { get; private set; } = "";
        /// 会話サーバーが返した様子：off・connecting・waiting（配信が始まるのを待つ）・live・error。届いていなければ空
        public string YouTubeState { get; private set; } = "";
        public string YouTubeReason { get; private set; } = "";
        public string YouTubeTitle { get; private set; } = "";
        public int YouTubeReceived { get; private set; }
        public int YouTubeReplied { get; private set; }

        void LoadYouTube()
        {
            YouTube = CielAppComposition.IsBroadcast && PlayerPrefs.GetInt(YouTubeOnKey, 0) == 1;
            YouTubeUrl = CielAppComposition.IsBroadcast ? PlayerPrefs.GetString(YouTubeUrlKey, "") : "";
        }

        /// URL とスイッチを変える（同じなら送らない）
        public void SetYouTube(string url, bool on)
        {
            if (!CielAppComposition.IsBroadcast) return;
            url = (url ?? "").Trim();
            if (url.Length == 0) on = false;
            if (url == YouTubeUrl && on == YouTube) return;
            (YouTubeUrl, YouTube) = (url, on);
            PlayerPrefs.SetString(YouTubeUrlKey, url);
            PlayerPrefs.SetInt(YouTubeOnKey, on ? 1 : 0);
            PlayerPrefs.Save();
            SendYouTube();
            Changed?.Invoke();
        }

        void SendYouTube()
        {
            if (_room == null || Status != State.Connected) return;
            // 切っているときも送る（会話サーバーがつないでいたら止める）。URL は JSON の文字として逃がす
            var json = $"{{\"v\":1,\"type\":\"youtube.link\",\"on\":{(YouTube ? "true" : "false")},\"url\":{JsonString(YouTubeUrl)}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.youtube"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 配信のコメントの設定を送れない: {e.Message}"); }
        }

        void OnYouTubeState(EventJson e)
        {
            (YouTubeState, YouTubeReason, YouTubeTitle) = (e.state ?? "", e.reason ?? "", e.title ?? "");
            (YouTubeReceived, YouTubeReplied) = (e.received, e.replied);
            Changed?.Invoke();
        }

        // 部屋を出たら、会話サーバーの様子は分からなくなる
        void ResetYouTube() => (YouTubeState, YouTubeReason, YouTubeTitle, YouTubeReceived, YouTubeReplied) = ("", "", "", 0, 0);
    }
}
