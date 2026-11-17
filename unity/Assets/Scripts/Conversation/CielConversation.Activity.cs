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
        public class ActivityLog
        {
            public int id;
            public float ago;
            public string text, kind;   // kind：ok・error・wait・info
        }

        [Serializable]
        public class ActivityBody
        {
            public int version, revision;
            public string session, phase, title, next_title, reason, last_title, last_phase, last_reason, last_note;
            public float for_s;
            public bool Active => !string.IsNullOrEmpty(phase) && phase != "idle" && phase != "unknown";
            public string Description => reason == "body_protocol_mismatch" ? "体のサービスの更新が必要です" : reason == "stop_timeout" ? "停止の確認に時間がかかっています"
                : reason == "defending" ? "身を守っています（作業を一時中断）"
                : reason == "eating" ? "食事をしています"
                : phase == "stopping" ? "前の作業を停止しています"
                : phase == "accepted" ? "依頼を受け付け、開始を待っています"
                : phase == "preparing" ? "材料・作業の条件を確認しています"
                : phase == "waiting" ? "作業の再開を待っています"
                : phase == "unknown" ? "体の状態を確認できていません"
                : phase == "running" ? "実行中：" + title : "今は作業していません";
        }

        [Serializable]
        public class ActivityController
        {
            public string phase, reason, outcome;
            public int step;
        }

        [Serializable]
        public class ActivityState
        {
            public string type, mind, who;   // mind：idle・listening・thinking・speaking。who：mind・talker
            public float mind_for;
            public int v, revision;
            public string stream_id;
            public float valid_for_s;
            public string thinking_origin;
            public ActivityController initiative, decision;
            public ActivityCall[] calls;
            public ActivityLog[] log;
            public ActivityBody body;
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
            catch (Exception) { InvalidateActivity(); return; }
            if (s == null || s.type != "activity.state" || s.v != 2 || string.IsNullOrEmpty(s.stream_id)
                || s.revision < 1 || float.IsNaN(s.valid_for_s) || s.valid_for_s <= 0 || s.valid_for_s > 6
                || s.initiative == null || s.decision == null
                || !(s.initiative.phase is "disabled" or "waiting" or "scheduled" or "deciding")
                || !(s.decision.phase is "idle" or "deciding" or "loading" or "calling" or "reviewing" or "finished" or "cancelled" or "failed")) { InvalidateActivity(); return; }
            if (_retiredActivity.Contains(s.stream_id)) return;
            if (_activityStream == s.stream_id && s.revision <= _activitySequence) return;
            if (!string.IsNullOrEmpty(_activityStream) && _activityStream != s.stream_id)
                _retiredActivity.Add(_activityStream);
            _activityStream = s.stream_id;
            _activitySequence = s.revision;
            // bodyの版1だけを受理する。欠落・不一致を別の表示形式で補わない。
            if (s.body == null || s.body.version != 1) s.body = new ActivityBody { version = 1, phase = "unknown", reason = "body_protocol_mismatch" };
            Activity = s;
            ActivityAt = Time.unscaledTime;
            ActivityRevision++;
            Changed?.Invoke();
        }

        /// 届いてからの秒数を足した、いまの秒数
        public float ActivitySeconds(float atSend) => atSend + (Time.unscaledTime - ActivityAt);
        readonly System.Collections.Generic.HashSet<string> _retiredActivity = new();
        string _activityStream;
        int _activitySequence;
        public bool ActivityFresh => CielActivityPresentation.Fresh(Activity, Time.unscaledTime - ActivityAt);

        void InvalidateActivity()
        {
            Activity = null;
            ActivityRevision++;
            Changed?.Invoke();
        }

        void ResetActivity()
        {
            Activity = null;
            _retiredActivity.Clear();
            _activityStream = null;
            _activitySequence = 0;
            ActivityRevision++;
        }
    }

    // 操作画面・配信映像・独立カードで同じ事実と文言を使う。
    public static class CielActivityPresentation
    {
        public static string Flow(CielConversation.ActivityState a, float age = 0)
        {
            var phase = Fresh(a, age) ? a.decision?.phase : "unknown";
            string Node(string label, bool active) => active ? "<color=#5BF0C8><b>● " + label + "</b></color>" : "<color=#8FB3C3>" + label + "</color>";
            return Node("待機", phase == "idle") + " → " + Node("判断", phase == "deciding") + " → "
                + Node("返答・終了", phase is "finished" or "cancelled" or "failed")
                + "\n　　　　↓　↑ 結果をもとに再判断\n"
                + Node("機能ロード／操作", phase is "loading" or "calling") + " → " + Node("結果確認", phase == "reviewing");
        }

        public static bool Fresh(CielConversation.ActivityState a, float age) => a != null && a.v == 2
            && a.valid_for_s > 0 && age >= 0 && age <= a.valid_for_s;

        public static string Decision(CielConversation.ActivityState a) => a?.decision?.phase switch {
            "deciding" => "返事・次の行動を判断中",
            "loading" => "使う機能を読み込み中",
            "calling" => "操作を実行・結果待ち",
            "reviewing" => "結果を受け取り、次の行動を確認中",
            "cancelled" => "判断を中断しました",
            "failed" => "判断を完了できませんでした",
            "finished" => a.decision.outcome switch {
                "none" => "追加の操作なし", "clarify" => "返答・確認待ち",
                "blocked" => "この条件では実行できません",
                "accepted" => "依頼を受付済み（完了とは別）",
                "complete" => "結果確認を終了", _ => "判断終了"
            },
            "idle" => "判断する入力を待っています", _ => "判断状態を確認できていません"
        };

        public static string Initiative(CielConversation.ActivityState a) => a?.initiative?.phase switch {
            "disabled" => "無効・停止中", "scheduled" => "判断の開始待ち", "deciding" => "自発的に話す・動く・黙るを判断中",
            "waiting" => a.initiative.reason switch {
                "conversation" => "会話を優先して待機", "mode" => "会話モード・歌・登録の条件で待機",
                "quiet" => "会話が落ち着くのを待機", "cooldown" => "連続判断を抑えて待機",
                "eligible_event" => "対象の出来事を待機", _ => "新しい発言・出来事を待機"
            }, _ => "有効状態を確認できていません"
        };

        public static string Outcome(CielConversation.ActivityState a) => a?.initiative?.outcome switch {
            "silent" => "今回は黙ると判断", "acted" => "行動を選択", "spoke" => "発話を選択",
            "cancelled" => "割り込みで中断", "error" => "判断エラー", _ => "まだ判断結果なし"
        };
    }
}
