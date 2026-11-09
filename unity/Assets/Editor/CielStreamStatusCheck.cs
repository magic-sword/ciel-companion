// Offline contract/consumer regression checks. Run via Unity -executeMethod.
using System;
using System.Reflection;
using System.Text;
using Ciel.Conversation;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielStreamStatusCheck
    {
        public static void Run()
        {
            var go = new GameObject("WorkDisplayCheck");
            int checks = 0;
            void Check(bool ok, string name) { if (!ok) throw new Exception("Work display: " + name); checks++; }
            try
            {
                var c = go.AddComponent<CielConversation>(); c.enabled = false;
                var receive = typeof(CielConversation).GetMethod("OnGoalData", BindingFlags.Instance | BindingFlags.NonPublic);
                var render = typeof(CielConversation).Assembly.GetType("Ciel.Conversation.CielConversationUI")
                    .GetMethod("StreamStatusText", BindingFlags.Static | BindingFlags.NonPublic);
                string Render(CielConversation.GoalState g, bool recent, string activity) => (string)render.Invoke(null, new object[] { g, recent, activity });
                var g = new CielConversation.GoalState { v = 2, type = "goal.state", stream_id = "a", revision = 1,
                    has_task = true, confirmed = true, valid_for_ms = 10000, receivedAt = Time.unscaledTime,
                    task = new CielConversation.WorkInfo { session = "server", task_id = "task", revision = 1,
                        title = "ツルハシを作る", state = "running", can_stop = true } };
                void Receive() => receive.Invoke(c, new object[] { Encoding.UTF8.GetBytes(JsonUtility.ToJson(g)) });
                Receive();
                Check(c.Goal.HasGoal && c.Goal.task.state == "running", "v2 received");
                Check(Render(c.Goal, false, "会話：話しています").Contains("ツルハシ") && Render(c.Goal, false, "会話：話しています").Contains("話しています"), "parallel output");
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
                Check(Render(c.Goal, true, "").Contains("できた"), "completion briefly visible");
                Check(Render(c.Goal, false, "") == "", "completion expires");
                Check(Render(null, false, "いま：<鉄>").Contains("＜鉄＞"), "rich text escaped");
                g.v = 1; Receive();
                Check(c.Goal.protocolError, "old wire version rejected");
                Debug.Log("STREAM_STATUS_CHECK_OK " + checks);
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }
    }
}
