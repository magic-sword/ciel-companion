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
        public class ActivityContinuation
        {
            public bool enabled;
            public string phase;
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
            public ActivityController decision;
            public ActivityContinuation continuation;
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
            if (s == null || s.type != "activity.state" || s.v != 3 || string.IsNullOrEmpty(s.stream_id)
                || s.revision < 1 || float.IsNaN(s.valid_for_s) || s.valid_for_s <= 0 || s.valid_for_s > 6
                || s.continuation == null || s.decision == null
                || !(s.continuation.phase is "waiting" or "responding" or "continuing" or "tool_result" or "cancelled" or "failed")
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
            var phase = Fresh(a, age) ? Position(a) : "unknown";
            string Node(string label, bool active) => active ? "<color=#5BF0C8><b>● " + label + "</b></color>" : "<color=#8FB3C3>" + label + "</color>";
            return Node("待機", phase == "idle") + " → " + Node("判断", phase == "deciding") + " → "
                + Node("発話を渡す", phase == "finished") + " → " + Node("続きの生成", phase == "continuing")
                + " → 待機／判断へ\n" + Node("中断", phase == "cancelled") + "　" + Node("エラー", phase == "failed")
                + "\n　　　　↓　↑ 結果をもとに再判断\n"
                + Node("機能ロード／操作", phase is "loading" or "calling") + " → " + Node("結果確認", phase == "reviewing");
        }

        public static bool Fresh(CielConversation.ActivityState a, float age) => a != null && a.v == 3
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

        public static string Continuation(CielConversation.ActivityState a) => a?.continuation?.phase switch {
            "responding" => "返事を生成中", "continuing" => "続きの発話を生成中",
            "tool_result" => "道具の結果から再判断中", "waiting" => "新しい発言・出来事を待機",
            "cancelled" => "会話の生成を中断", "failed" => "会話の生成でエラー",
            _ => "会話の進行を確認できていません"
        };

        public static string Audio(CielConversation.ActivityState a) => a?.mind switch {
            "speaking" => "話しています", "listening" => "入力を受け付けています",
            "thinking" => "音声を準備中", _ => "発話していません"
        };
        public static string Setting(CielConversation.ActivityState a) => a?.continuation == null
            ? "継続設定：未確認" : a.continuation.enabled ? "発話の継続：有効" : "発話の継続：無効";

        public static string Position(CielConversation.ActivityState a) {
            if (a?.decision?.phase is "cancelled" or "failed") return a.decision.phase;
            if (a?.decision?.phase is "loading" or "calling" or "reviewing") return a.decision.phase;
            if (a?.continuation?.phase == "waiting") return "idle";
            if (a?.continuation?.phase == "continuing") return "continuing";
            return a?.decision?.phase ?? "idle";
        }
    }
}
