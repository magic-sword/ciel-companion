// goal.state v2 の受け取りと、作業の表示文の回帰確認。Unity の -executeMethod で走らせる（CielAppCompositionCheck からも呼ぶ）。
using System;
using System.Reflection;
using System.Text;
using Ciel.Conversation;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielGoalStateCheck
    {
        public static void Run()
        {
            var go = new GameObject("GoalStateCheck");
            int checks = 0;
            void Check(bool ok, string name) { if (!ok) throw new Exception("Goal state: " + name); checks++; }
            try
            {
                var c = go.AddComponent<CielConversation>(); c.enabled = false;
                var receive = typeof(CielConversation).GetMethod("OnGoalData", BindingFlags.Instance | BindingFlags.NonPublic);
                var g = new CielConversation.GoalState { v = 2, type = "goal.state", stream_id = "a", revision = 1,
                    has_task = true, confirmed = true, valid_for_ms = 10000, receivedAt = Time.unscaledTime,
                    task = new CielConversation.WorkInfo { session = "server", task_id = "task", revision = 1,
                        title = "ツルハシを作る", state = "running", can_stop = true } };
                void Receive() => receive.Invoke(c, new object[] { Encoding.UTF8.GetBytes(JsonUtility.ToJson(g)) });
                Receive();
                Check(c.Goal.HasGoal && c.Goal.task.state == "running", "v2 received");
                Check(CielWorkPresentation.From(c.Goal).Summary.Contains("ツルハシ"), "running work shown");
                g.revision = 0; g.task.title = "古い通知"; Receive();
                Check(c.Goal.protocolError, "invalid revision is unknown");
                g.revision = 2; g.task.title = "ツルハシを作る"; Receive();
                Check(!c.Goal.protocolError, "valid confirmation restores display");
                g.revision = 1; g.task.title = "古い通知"; Receive();
                Check(c.Goal.task.title == "ツルハシを作る", "out of order rejected");
                g.stream_id = "b"; g.revision = 1; Receive();
                Check(c.Goal.stream_id == "b", "new service stream");
                g.stream_id = "a"; g.revision = 3; Receive();
                Check(c.Goal.stream_id == "b", "retired stream rejected");
                g.stream_id = "b"; g.revision = 2; g.task.state = "succeeded"; Receive();
                Check(CielWorkPresentation.From(c.Goal).Summary.Contains("処理終了"), "completion shown without claiming the goal");
                g.v = 1; Receive();
                Check(c.Goal.protocolError, "old wire version rejected");
                Debug.Log("GOAL_STATE_CHECK_OK " + checks);
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }
    }
}
