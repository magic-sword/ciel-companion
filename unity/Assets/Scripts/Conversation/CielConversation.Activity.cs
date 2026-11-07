// 会話（CielConversation）のうち、いまのシエル（会話サーバーの activity.py が送る activity.state）。
// 心が考えている・道具の結果を待っている・体が技をしている、を外から見えるようにする（止まって見えたとき、どこで待っているかが
// 分からなかった。2026-11-07）。ゲームを問わない形なので、ここもゲームのことは知らない（見せる言葉と秒数だけで描く）。
// 経った秒数は、届いたときの値に、届いてからの時間を足して数える。読むのは CielConversationUI.Activity.cs。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        [Serializable]
        public class ActivityCall
        {
            public string label;
            public float for_s;
        }

        [Serializable]
        public class ActivityTask
        {
            public string title;
            public float for_s;
        }

        [Serializable]
        public class ActivityLog
        {
            public int id;
            public float ago;
            public string text, kind;   // kind：ok・error・wait・info
        }

        [Serializable]
        public class ActivityState
        {
            public string type, mind, who, doing, goal_step;   // mind：idle・listening・thinking・speaking。who：mind・talker
            public float mind_for;
            public ActivityCall[] calls;
            public ActivityTask[] tasks;
            public ActivityLog[] log;
        }

        /// いまのシエル（届いていなければ null）
        public ActivityState Activity { get; private set; }
        /// Activity が届いた時刻（経った秒数を数え足す）
        public float ActivityAt { get; private set; }
        /// 届いた回数（画面が変わったことに気づく）
        public int ActivityRevision { get; private set; }

        void OnActivity(byte[] data)
        {
            ActivityState s;
            try { s = JsonUtility.FromJson<ActivityState>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] いまのシエルを読めない: {ex.Message}"); return; }
            if (s == null || s.type != "activity.state") return;
            Activity = s;
            ActivityAt = Time.unscaledTime;
            ActivityRevision++;
            Changed?.Invoke();
        }

        /// 届いてからの秒数を足した、いまの秒数
        public float ActivitySeconds(float atSend) => atSend + (Time.unscaledTime - ActivityAt);

        void ResetActivity()
        {
            Activity = null;
            ActivityRevision++;
        }
    }
}
