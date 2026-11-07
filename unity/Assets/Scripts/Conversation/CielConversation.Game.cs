// 会話（CielConversation）のうち、ゲームで一緒に遊ぶか（docs/game-environment-mcp-design-ja.md の 6.4）。
// アプリはゲームの名前を持たない。会話サーバーが、つなげるゲームの一覧（env.list：game・label）を送り、設定画面はその名前で
// スイッチを出す。スイッチはゲームごとに覚え（PlayerPrefs の ciel.game.<game>）、つないだとき・会話サーバーが入ってきたとき・
// 変えたときに env.link（game・on）を送る（topic ciel.game。server/agent/game_env.py）。オンのときだけ、会話サーバーが
// シエルの体を受け持つ。体を受け持ったか・ゲームの中にいるかは env.state（linked・playing・reason）で返る。
// 以前の会話サーバー（env.list を送らない）には、以前の形（game.link・game.state）でつなぐ。E6 で消す。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const string LegacyGamePrefKey = "ciel.minecraft";   // 以前の会話サーバーとつなぐとき・ゲームごとの値がまだ無いとき
        const string GamePrefPrefix = "ciel.game.";

        [Serializable]
        class EnvGame
        {
            public string game, label;
        }

        [Serializable]
        class EnvList
        {
            public string type;
            public EnvGame[] games;
        }

        /// 一緒に遊ぶか（設定画面のスイッチ）
        public bool GameWanted { get; private set; }
        /// 会話サーバーがつなげるゲーム（env.list の最初の 1 つ。今の会話サーバーは 1 つだけつなぐ）。分からなければ空
        public string GameName { get; private set; } = "";
        /// ゲームの見せる名前（「マイクラ」）。以前の会話サーバーでは空
        public string GameLabel { get; private set; } = "";
        /// 会話サーバーから env.list が届いた（新しい会話サーバー）。届いても、つなげるゲームが無ければ GameName は空
        public bool GameListed { get; private set; }
        /// 会話サーバーが体を受け持っているか・シエルがゲームの中にいるか・受け持っていない理由（busy・unavailable・off・connecting）
        public bool GameLinked { get; private set; }
        public bool GameInWorld { get; private set; }
        public string GameReason { get; private set; } = "";
        /// 会話サーバーから env.state か game.state が届いたか（古い会話サーバーは送らない）
        public bool GameKnown { get; private set; }
        float _gameWaitFrom = -1f;
        public float GameWaitingSeconds => _gameWaitFrom < 0 ? 0 : Mathf.Max(0, Time.unscaledTime - _gameWaitFrom);

        void LoadGame() => GameWanted = PlayerPrefs.GetInt(LegacyGamePrefKey, 0) == 1;

        public void SetGameWanted(bool on)
        {
            if (on == GameWanted) return;
            GameWanted = on;
            _gameWaitFrom = -1f;
            if (GameName != "") PlayerPrefs.SetInt(GamePrefPrefix + GameName, on ? 1 : 0);
            PlayerPrefs.SetInt(LegacyGamePrefKey, on ? 1 : 0);
            PlayerPrefs.Save();
            SendGame();
            Changed?.Invoke();
        }

        void SendGame()
        {
            if (_room == null || Status != State.Connected) return;
            if (GameWanted && _gameWaitFrom < 0) _gameWaitFrom = Time.unscaledTime;
            string json;
            if (GameListed)
            {
                if (GameName == "") return;   // この会話サーバーには、つなげるゲームが無い
                json = $"{{\"v\":1,\"type\":\"env.link\",\"game\":\"{GameName}\",\"on\":{(GameWanted ? "true" : "false")}}}";
            }
            else json = $"{{\"v\":1,\"type\":\"game.link\",\"on\":{(GameWanted ? "true" : "false")}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.game"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] ゲームの設定を送れない: {e.Message}"); }
        }

        // 設定のオン・オフを変えずに再要求する。他の会話の接続を解除しない。
        public void RetryGameConnection()
        {
            if (!GameWanted || Status != State.Connected || GameLinked || (GameListed && GameName == "")) return;
            (GameKnown, GameLinked, GameInWorld, GameReason) = (false, false, false, "connecting");
            _gameWaitFrom = Time.unscaledTime;
            SendGame();
            Changed?.Invoke();
        }

        // つなげるゲームの一覧（会話サーバーが、つないだ直後と device.hello_request の前に送る）
        void OnEnvList(byte[] data)
        {
            EnvList list;
            try { list = JsonUtility.FromJson<EnvList>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] ゲームの一覧を読めない: {ex.Message}"); return; }
            var first = list?.games != null && list.games.Length > 0 ? list.games[0] : null;
            var name = first != null && IsGameName(first.game) ? first.game : "";
            var changed = !GameListed || name != GameName;
            GameListed = true;
            GameName = name;
            GameLabel = first?.label ?? "";
            if (name != "")
            {
                var key = GamePrefPrefix + name;
                GameWanted = PlayerPrefs.HasKey(key) ? PlayerPrefs.GetInt(key, 0) == 1 : PlayerPrefs.GetInt(LegacyGamePrefKey, 0) == 1;
            }
            Debug.Log($"[CielConversation] つなげるゲーム：{(name != "" ? $"{GameLabel}（{name}）" : "なし")}");
            if (changed) SendGame();
            Changed?.Invoke();
        }

        // ゲームの名前は JSON にそのまま書くので、英数字と _ だけを受け取る
        static bool IsGameName(string s)
        {
            if (string.IsNullOrEmpty(s) || s.Length > 32) return false;
            foreach (var ch in s)
                if (!(ch >= 'a' && ch <= 'z' || ch >= '0' && ch <= '9' || ch == '_')) return false;
            return true;
        }

        void OnEnvState(EventJson e)
        {
            if (e.game != GameName) return;
            if (!string.IsNullOrEmpty(e.label)) GameLabel = e.label;
            SetGameState(e.linked, e.playing, e.reason);
        }

        // 以前の会話サーバーの知らせ。新しい会話サーバーは env.state も送るので、一覧が届いていれば見ない
        void OnGameState(EventJson e)
        {
            if (GameListed) return;
            SetGameState(e.linked, e.in_world, e.reason);
        }

        void SetGameState(bool linked, bool inWorld, string reason)
        {
            if (!GameKnown || linked != GameLinked || inWorld != GameInWorld || (reason ?? "") != GameReason)
                _gameWaitFrom = Time.unscaledTime;
            (GameKnown, GameLinked, GameInWorld, GameReason) = (true, linked, inWorld, reason ?? "");
            Debug.Log($"[CielConversation] ゲーム：{(GameLinked ? (GameInWorld ? "入っている" : "体とつながった") : $"つながっていない（{GameReason}）")}");
            Changed?.Invoke();
        }

        // 部屋を出たら、体とのつながりも、つなげるゲームも分からなくなる（つなぎ直した会話サーバーが送り直す）
        void ResetGame()
        {
            _gameWaitFrom = -1f;
            (GameKnown, GameLinked, GameInWorld, GameReason) = (false, false, false, "");
            (GameListed, GameName, GameLabel) = (false, "", "");
        }
    }
}
