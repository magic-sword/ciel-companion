// 配信用の札の回帰確認。Unity -batchmode -executeMethod Ciel.EditorTools.CielStreamStatusCheck.Run -quit
// 会話サーバーへの接続なしで、目的の完了後に直接の作業を頼む流れを確認する。
using System;
using System.Reflection;
using System.Text;
using Ciel.Conversation;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielStreamStatusCheck
    {
        const BindingFlags StaticPrivate = BindingFlags.Static | BindingFlags.NonPublic;

        public static void Run()
        {
            var go = new GameObject("StreamStatusCheck");
            try
            {
                var c = go.AddComponent<CielConversation>();
                c.enabled = false;
                var ui = typeof(CielConversation).Assembly.GetType("Ciel.Conversation.CielConversationUI");
                var render = ui.GetMethod("StreamStatusText", StaticPrivate);
                var chip = ui.GetMethod("ActivityChip", StaticPrivate);
                var receive = typeof(CielConversation).GetMethod("OnActivity", BindingFlags.Instance | BindingFlags.NonPublic);

                string Activity(string json)
                {
                    receive.Invoke(c, new object[] { Encoding.UTF8.GetBytes(json) });
                    var result = ((string text, Color color, bool show))chip.Invoke(null, new object[] { c, c.Activity, true });
                    return result.text;
                }
                string Render(CielConversation.GoalState goal, bool recent, string current) =>
                    (string)render.Invoke(null, new object[] { goal, recent, current });
                void Check(bool ok, string name)
                {
                    if (!ok) throw new Exception("Stream status regression: " + name);
                }

                var goal = new CielConversation.GoalState {
                    goal = new CielConversation.GoalInfo { id = 1, title = "ツルハシを作る", status = "done", game_label = "マイクラ" }
                };
                Check(Render(goal, true, "").Contains("できた！"), "completed goal remains briefly");
                Check(Render(goal, false, "") == "", "completed goal expires");

                var first = Activity("{\"type\":\"activity.state\",\"mind\":\"listening\",\"tasks\":[{\"title\":\"鉄を探す\",\"for_s\":2}]}");
                Check(Render(goal, false, first).Contains("鉄を探す"), "next task appears after goal expires");
                Check(!Render(goal, true, first).Contains("ツルハシを作る"), "new task replaces recently completed goal");

                var next = Activity("{\"type\":\"activity.state\",\"mind\":\"listening\",\"tasks\":[{\"title\":\"鉄を集める\",\"for_s\":1}]}");
                Check(Render(goal, false, next).Contains("鉄を集める") && !Render(goal, false, next).Contains("鉄を探す"),
                    "subsequent task updates with the same goal object");

                goal.goal.status = "running";
                var both = Render(goal, false, next);
                Check(both.Contains("ツルハシを作る") && both.Contains("鉄を集める"), "active goal and current task are shown together");
                Check(Render(null, false, next).Contains("鉄を集める"), "task without any goal appears");
                Check(Render(null, false, "いま：<鉄>").Contains("＜鉄＞"), "task title escapes rich text");

                var idle = Activity("{\"type\":\"activity.state\",\"mind\":\"listening\",\"log\":[{\"text\":\"内部の知らせ\",\"ago\":0}]}");
                Check(Render(null, false, idle) == "", "idle state and internal log do not leave a stale card");
                Debug.Log("STREAM_STATUS_CHECK_OK (9 checks)");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }
    }
}
