// 会話（CielConversation）のうち、マイクラで一緒に遊ぶか（docs/minecraft-design-ja.md）。
// 設定画面のスイッチで選び（PlayerPrefs）、つないだとき・会話サーバーが入ってきたとき・変えたときに、会話サーバーへ送る
// （topic ciel.game。server/agent/minecraft.py）。オンのときだけ、会話サーバーがシエルの体（server/minecraft）へつなぐ。
// 体とつながったか・マイクラに入っているかは、会話サーバーが game.state で返す（GameLinked・GameInWorld・GameReason）。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string GamePrefKey = "ciel.minecraft";

        /// マイクラで一緒に遊ぶか（設定画面のスイッチ）
        public bool Minecraft { get; private set; }
        /// 会話サーバーがシエルの体とつながっているか・シエルがマイクラに入っているか・つながらない理由（busy・unavailable・off）
        public bool GameLinked { get; private set; }
        public bool GameInWorld { get; private set; }
        public string GameReason { get; private set; } = "";
        /// 会話サーバーから game.state が届いたか（古い会話サーバーは送らない）
        public bool GameKnown { get; private set; }

        void LoadGame() => Minecraft = PlayerPrefs.GetInt(GamePrefKey, 0) == 1;

        public void SetMinecraft(bool on)
        {
            if (on == Minecraft) return;
            Minecraft = on;
            PlayerPrefs.SetInt(GamePrefKey, on ? 1 : 0);
            PlayerPrefs.Save();
            SendGame();
            Changed?.Invoke();
        }

        void SendGame()
        {
            if (_room == null || Status != State.Connected) return;
            var json = $"{{\"v\":1,\"type\":\"game.link\",\"on\":{(Minecraft ? "true" : "false")}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.game"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] マイクラの設定を送れない: {e.Message}"); }
        }

        void OnGameState(EventJson e)
        {
            (GameKnown, GameLinked, GameInWorld, GameReason) = (true, e.linked, e.in_world, e.reason ?? "");
            Debug.Log($"[CielConversation] マイクラ：{(GameLinked ? (GameInWorld ? "入っている" : "体とつながった") : $"つながっていない（{GameReason}）")}");
            Changed?.Invoke();
        }

        // 部屋を出たら、体とのつながりは分からなくなる
        void ResetGame() => (GameKnown, GameLinked, GameInWorld, GameReason) = (false, false, false, "");
    }
}
