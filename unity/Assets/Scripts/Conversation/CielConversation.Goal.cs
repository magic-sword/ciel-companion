// 会話（CielConversation）のうち、シエルの今の目的（長い目的をやり遂げる仕組み。docs/goal-runner-design-ja.md の 4 章）。
// 会話サーバーの目的の係（server/agent/goals.py）が、目的・段・進み具合・直したこと・あとでやる目的が変わるたびに、
// goal.state を送る（topic ciel.goal）。ゲームを問わない形なので、ここもゲームのことは知らない（label・status・progress だけで描く）。
// 操作用の画面の札とパネル・配信用のウィンドウの札（CielConversationUI.Goal.cs）が Goal を読む。
// 「止める」「続ける」は goal.control で返す（会話サーバーの goals.py の on_data）。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        [Serializable]
        public class GoalInfo
        {
            public int id;
            public bool can_resume;
            public string task_id;
            public string game, game_label, title, by, by_label, status, why;
        }

        [Serializable]
        public class GoalStep
        {
            public int id;
            public string label, status;   // status：todo・running・done・failed・skipped
            public int[] progress;          // [できた数, 目標の数]（数で確かめられる段だけ。無ければ空）
        }

        [Serializable]
        public class GoalState
        {
            public string type;
            public GoalInfo goal;
            public string[] path;          // いちばん上の目的から、今いる小さな目標までの名前（小さな目標が無ければ 1 つ）
            public GoalStep[] steps;       // 今いる目標（小さな目標があれば、いちばん下）の段
            public string[] changes, next;
            public string attention;

            /// 今いる小さな目標までの道筋（「作業台を置く場所を空ける」。いちばん上の目的だけなら null）
            public string SubPath => path != null && path.Length > 1 ? string.Join(" › ", path, 1, path.Length - 1) : null;
            /// 目的があるか（goal が null のときも、JsonUtility は空の GoalInfo を作る）
            public bool HasGoal => goal != null && goal.id > 0 && !string.IsNullOrEmpty(goal.title);
            /// 動いている・止まって待っている（planning・running・paused）
            public bool Active => HasGoal && (goal.status == "planning" || goal.status == "running" || goal.status == "paused");
        }

        /// 今の目的（会話サーバーから届いた最新の goal.state。届いていなければ null）
        public GoalState Goal { get; private set; }
        /// Goal が届いた・変わった時刻（できた・やめたの札を少しのあいだ見せる）
        public float GoalSince { get; private set; }

        void OnGoalData(byte[] data)
        {
            GoalState s;
            try { s = JsonUtility.FromJson<GoalState>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] 目的の知らせを読めない: {ex.Message}"); return; }
            if (s == null || s.type != "goal.state") return;
            var before = Goal;
            Goal = s;
            if (before == null || !before.HasGoal || !s.HasGoal || before.goal.id != s.goal.id || before.goal.status != s.goal.status)
                GoalSince = Time.unscaledTime;
            Changed?.Invoke();
        }

        /// 「止める」（stop）・「続ける」（resume）。会話サーバーの目的の係が受ける
        public void SendGoalControl(string action)
        {
            if (_room == null || Status != State.Connected) return;
            var json = $"{{\"v\":1,\"type\":\"goal.control\",\"action\":\"{action}\"}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.goal"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 目的の操作を送れない: {e.Message}"); }
        }

        // 部屋を出たら、目的は分からなくなる（会話サーバーの目的の係は会話ごと）
        void ResetGoal() => Goal = null;
    }
}
