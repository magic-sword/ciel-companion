namespace Ciel.Conversation
{
    // 操作者向けの接続診断。会話への接続と、ゲームの体への接続を区別する。
    public sealed class CielBroadcastNotice
    {
        public enum Action { None, RetryGame, Reconnect, Connect, Settings }
        public string title = "", detail = "", button = "";
        public bool error;
        public Action action;
        public bool Visible => title.Length > 0;

        static CielBroadcastNotice Make(string title, string detail, string button = "", Action action = Action.None, bool error = false) =>
            new CielBroadcastNotice { title = title, detail = detail, button = button, action = action, error = error };

        public static CielBroadcastNotice From(CielConversation c, float? waitingSeconds = null)
        {
            if (c.Status == CielConversation.State.Failed)
                return Make("会話に接続できません", "通信状態と接続設定を確認して、もう一度接続してください。", "再接続", Action.Connect, true);
            if (c.Status != CielConversation.State.Connected) return new CielBroadcastNotice();
            if (c.AgentMissing != "")
                return Make("会話サーバーから応答がありません", "会話の接続先でシエルが応答していません。サーバーの稼働状態を確認してください。", "再接続", Action.Reconnect, true);
            if (c.Problem != "")
            {
                string reason = c.Problem == "quota" ? "利用上限・残高不足" : c.Problem == "auth" ? "認証エラー"
                    : c.Problem == "rate_limit" ? "サービスの混雑・呼び出し制限" : "処理エラー";
                string service = c.ProblemService == "stt" ? "聞き取り" : c.ProblemService == "tts" ? "読み上げ"
                    : c.ProblemService == "llm" ? "返事の生成" : "シエルの処理";
                return Make(service + "で問題が発生しています", reason + (c.ProblemStopped ? "。会話が停止しています。" : "。直近の処理が失敗しました。"),
                    c.ProblemStopped && c.Problem != "quota" && c.Problem != "auth" ? "再接続" : "設定を開く",
                    c.ProblemStopped && c.Problem != "quota" && c.Problem != "auth" ? Action.Reconnect : Action.Settings, true);
            }
            if (!c.GameWanted) return new CielBroadcastNotice();
            string game = string.IsNullOrEmpty(c.GameLabel) ? "ゲーム" : c.GameLabel;
            if (c.GameListed && c.GameName == "")
                return Make("ゲームの接続先がありません", "この会話サーバーには、つなげるゲームが登録されていません。", "設定を開く", Action.Settings, true);
            if (c.GameLinked && c.GameInWorld) return new CielBroadcastNotice();
            if (c.GameKnown && c.GameReason == "busy" && !c.GameLinked)
                return Make(game + "に接続できていません", "別の会話がシエルの体を使用中と返りました。相手の接続が終わったら再試行してください。", "接続を再試行", Action.RetryGame);
            if (c.GameKnown && c.GameReason == "unavailable" && !c.GameLinked)
                return Make(game + "の接続が利用できません", "会話は接続済みですが、ゲームとの接続を利用できません。サーバーと設定を確認してください。", "接続を再試行", Action.RetryGame, true);
            if (c.GameLinked)
                return Make(game + "への参加を待っています", "体との接続は済んでいますが、ゲーム内にはまだ入れていません。", "設定を開く", Action.Settings);
            if (c.GameKnown && c.GameReason != "connecting")
                return Make(game + "との接続が切れています", "会話は接続済みですが、ゲームの体には接続できていません。", "接続を再試行", Action.RetryGame);
            int seconds = (int)(waitingSeconds ?? c.GameWaitingSeconds);
            if (seconds >= 15)
                return Make(game + "の接続に時間がかかっています", $"{seconds}秒間、接続完了の通知を待っています。サーバーの状態を確認して再試行してください。", "接続を再試行", Action.RetryGame);
            return Make(game + "に接続しています", "会話は接続済みです。ゲームの体からの応答を待っています。");
        }
    }
}
