// goal.state / goal.control v2. Work state belongs to the service; presentation is shared by all outputs.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        [Serializable]
        public class WorkInfo
        {
            public string session, task_id, state, service, service_label, title, message, reason;
            public string decision_id, decision_message;
            public int revision, remaining_ms;
            public bool remaining_known, can_stop, can_retry;
        }

        [Serializable]
        public class GoalState
        {
            public int v, revision, confirmed_ago_ms, valid_for_ms;
            public string type, stream_id;
            public bool confirmed, has_task;
            public WorkInfo task;
            [NonSerialized] public float receivedAt;
            [NonSerialized] public bool protocolError;
            public bool HasGoal => has_task && task != null && !string.IsNullOrEmpty(task.task_id);
            public bool Active => protocolError || (HasGoal && !Terminal(task.state));
            public static bool Terminal(string state) => state == "succeeded" || state == "failed" || state == "cancelled";
            public static bool Known(string state) => Terminal(state) || state == "accepted" || state == "running" || state == "needs_decision" || state == "cancelling";
            public bool Fresh => !protocolError && confirmed && valid_for_ms > 0 &&
                confirmed_ago_ms + Math.Max(0, Time.unscaledTime - receivedAt) * 1000 < valid_for_ms;
        }

        public GoalState Goal { get; private set; }
        public float GoalSince { get; private set; }
        readonly HashSet<string> _retiredWorkStreams = new HashSet<string>();

        void OnGoalData(byte[] data)
        {
            GoalState s;
            try { s = JsonUtility.FromJson<GoalState>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception) { WorkProtocolError(); return; }
            if (s == null || s.v != 2 || s.type != "goal.state" || string.IsNullOrEmpty(s.stream_id)
                || s.revision <= 0 || s.valid_for_ms != 10000 || s.confirmed_ago_ms < 0
                || (s.has_task && (s.task == null || string.IsNullOrEmpty(s.task.task_id) ||
                    !GoalState.Known(s.task.state) || string.IsNullOrEmpty(s.task.session) || s.task.revision <= 0))
                || (!s.has_task && !string.IsNullOrEmpty(s.task?.task_id)))
            { WorkProtocolError(); return; }
            var before = Goal;
            if (_retiredWorkStreams.Contains(s.stream_id)) return;
            if (before != null && !string.IsNullOrEmpty(before.stream_id))
            {
                if (before.stream_id == s.stream_id && s.revision <= before.revision) return;
                if (before.stream_id != s.stream_id) _retiredWorkStreams.Add(before.stream_id);
            }
            s.receivedAt = Time.unscaledTime;
            Goal = s;
            if (before == null || before.task?.task_id != s.task?.task_id || before.task?.state != s.task?.state)
                GoalSince = Time.unscaledTime;
            Changed?.Invoke();
        }

        void WorkProtocolError()
        {
            // Preserve the last identity so a targeted stop is still possible; never claim idle or stopped.
            if (Goal != null) Goal.protocolError = true;
            else Goal = new GoalState { protocolError = true };
            Changed?.Invoke();
        }

        [Serializable]
        class WorkControl
        {
            public int v = 2, revision;
            public string type = "goal.control", stream_id, session, task_id, decision_id, action;
        }

        public void SendGoalControl(string action, GoalState target)
        {
            var g = Goal;
            var view = CielWorkPresentation.From(g);
            if (target?.task == null || g?.task == null || target.stream_id != g.stream_id
                || target.task.session != g.task.session || target.task.task_id != g.task.task_id
                || target.task.revision != g.task.revision || target.task.decision_id != g.task.decision_id) return;
            if (_room == null || Status != State.Connected || g?.task == null
                || (action != "stop" && action != "retry")
                || (action == "stop" ? !view.canStop : !view.canRetry)) return;
            var control = new WorkControl { stream_id = g.stream_id, session = g.task.session,
                task_id = g.task.task_id, revision = g.task.revision, decision_id = g.task.decision_id, action = action };
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(JsonUtility.ToJson(control)), reliable: true, topic: "ciel.goal"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 作業の操作を送れない: {e.Message}"); }
        }

        void ResetGoal() { Goal = null; _retiredWorkStreams.Clear(); }
    }

    // No inferred steps, percentages or completion estimates. Budget is a limit, not an ETA.
    public sealed class CielWorkPresentation
    {
        public string title = "", status = "", message = "", budget = "", phase = "unknown";
        public bool visible, attention, canStop, canRetry;
        public static CielWorkPresentation From(CielConversation.GoalState g)
        {
            var p = new CielWorkPresentation();
            if (g == null) return p;
            if (!g.HasGoal && !g.protocolError) return p;
            p.visible = true;
            var w = g.task;
            p.title = string.IsNullOrEmpty(w?.title) ? "作業の状態" : w.title;
            p.phase = w?.state ?? "unknown";
            p.status = p.phase switch {
                "accepted" => "受付済み・開始待ち", "running" => "実行中", "needs_decision" => "判断待ち",
                "cancelling" => "停止確認中", "succeeded" => "できた！", "failed" => "完了できませんでした",
                "cancelled" => "停止を確認しました", _ => "状態不明"
            };
            p.attention = p.phase == "needs_decision" || p.phase == "failed" || p.phase == "cancelling";
            p.message = w?.message ?? "";
            if (p.phase == "accepted" && p.message.Length == 0) p.message = "依頼を受け付け、開始を待っています";
            if (p.phase == "running" && p.message.Length == 0) p.message = "作業先で実行しています";
            if (p.phase == "needs_decision" && !string.IsNullOrEmpty(w?.decision_message)) p.message = w.decision_message;
            if (p.phase == "cancelling" && string.IsNullOrEmpty(p.message)) p.message = "実際に停止したことを確認しています";
            if (!g.Fresh && (g.Active || g.protocolError))
            {
                p.status = "状態不明・停止未確認";
                p.message = g.protocolError ? "状態通知の形式を確認できません" : "作業先の最新状態を確認できていません";
                p.phase = "unknown"; p.attention = true;
            }
            p.canStop = g.HasGoal && !CielConversation.GoalState.Terminal(w.state) && w.state != "cancelling" && w.can_stop;
            p.canRetry = g.Fresh && w != null && w.state == "needs_decision" && w.can_retry && !string.IsNullOrEmpty(w.decision_id);
            if (g.Fresh && g.Active && w != null && w.remaining_known)
            {
                int left = Math.Max(0, w.remaining_ms - (int)(Math.Max(0, Time.unscaledTime - g.receivedAt) * 1000));
                p.budget = $"実行予算の残り {(int)Math.Ceiling(left / 1000.0)}秒（完了予測ではありません）";
            }
            return p;
        }
        public string Summary => string.Join("\n", Array.FindAll(new[] { title, status, message, budget }, s => !string.IsNullOrEmpty(s)));
    }
}
