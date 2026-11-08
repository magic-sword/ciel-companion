// 受信した事実から表示する。待機・思考・道具の返答待ち・体の実行を区別する。
using System;

namespace Ciel.Conversation
{
    public sealed class CielAudienceCardState
    {
        public bool visible = true, attention;
        public string heading = "シエル｜待機中", title = "今は作業していません", current = "次の呼びかけ・依頼を待っています";
        public string progress = "", elapsed = "", phase = "idle";
        public float fraction = -1;

        static string Seconds(float value, float age) => $"{Math.Max(0, (int)(value + age))}秒経過";

        public static CielAudienceCardState From(CielConversation.GoalState goal,
            CielConversation.ActivityState activity, bool connected, bool recent, float age = 0, bool userSpeaking = false)
        {
            var result = new CielAudienceCardState();
            if (!connected)
            {
                result.phase = "disconnected";
                result.heading = "シエル｜未接続";
                result.title = "会話に接続していません";
                result.current = "操作画面で接続を確認してください";
                result.attention = true;
                return result;
            }
            var body = activity?.body;
            string work = body != null && body.Active ? body.title : null;
            string summary = "";
            if (body != null && body.phase != "idle" && body.phase != "running")
            {
                result.phase = body.phase;
                result.heading = body.phase == "stopping" ? "シエル｜作業の切り替え中"
                    : body.phase == "unknown" ? "シエル｜体の状態不明" : "シエル｜作業の開始・再開待ち";
                result.title = !string.IsNullOrEmpty(body.next_title) ? body.next_title
                    : !string.IsNullOrEmpty(body.title) ? body.title : "体の状態を確認しています";
                result.current = summary = body.Description;
                result.elapsed = Seconds(body.for_s, age);
                result.attention = body.reason == "stop_timeout" || body.phase == "unknown";
            }
            else if (activity?.calls?.Length > 0)
            {
                var call = activity.calls[0];
                result.phase = "calling";
                result.heading = "シエル｜道具の返答待ち";
                result.title = call.label;
                result.current = "道具を呼び出し、返答を待っています";
                summary = call.label + "の実行開始・結果待ち";
                result.progress = string.IsNullOrEmpty(work) ? "実行開始はまだ確認できていません" : "体の作業：" + work;
                result.elapsed = Seconds(call.for_s, age);
                result.attention = call.for_s + age >= 30;
                if (result.attention) result.current = "道具の返答待ちが続いています";
            }
            else if (!string.IsNullOrEmpty(work))
            {
                result.phase = "working";
                result.heading = "シエル｜作業中";
                result.title = work;
                result.current = body.Description;
                summary = "実行中：" + work;
                result.elapsed = Seconds(body.for_s, age);
            }
            else if (userSpeaking)
            {
                result.phase = "listening";
                result.heading = "シエル｜聞き取り中";
                result.title = "話を聞いています";
                result.current = "声を受け取っています";
            }
            else if (activity?.mind == "thinking")
            {
                result.phase = "thinking";
                bool initiative = activity.thinking_origin == "initiative";
                result.heading = initiative ? "シエル｜自発的に考え中" : "シエル｜考え中";
                result.title = initiative ? "自分から話すことを考えています"
                    : activity.thinking_origin == "tool_result" ? "道具の結果を確認しています"
                    : activity.thinking_origin == "comment" ? "コメントへの返事を考えています" : "返事・次の行動を考えています";
                result.current = "道具の呼び出しはまだありません";
                result.elapsed = Seconds(activity.mind_for, age);
                summary = result.title;
            }
            else if (activity?.mind == "speaking")
            {
                result.phase = "speaking";
                result.heading = "シエル｜発話中";
                result.title = "話しています";
                result.current = "声で返事をしています";
            }
            else if (activity?.background_thinking == true)
            {
                result.phase = "background";
                result.heading = "シエル｜自発的に考え中";
                result.title = "裏で考えを整理しています";
                result.current = "体の作業・道具の呼び出しはありません";
                result.elapsed = Seconds(activity.background_for, age);
                summary = result.title;
            }
            else if (activity == null)
            {
                result.phase = "unknown";
                result.heading = "シエル｜状態の確認中";
                result.title = "状態の通知を待っています";
                result.current = "まだ待機中かどうかは分かりません";
            }
            else if (activity.detail_version < 1)
            {
                result.current = "実行中の作業はありません";
                result.progress = "詳しい思考状態はまだ確認できていません";
            }

            if (body?.phase == "idle" && body.last_phase == "failed" && result.phase == "idle")
            {
                result.phase = "failed";
                result.heading = "シエル｜作業できませんでした";
                result.title = string.IsNullOrEmpty(body.last_title) ? "直前の作業" : body.last_title;
                result.current = string.IsNullOrEmpty(body.last_note) ? "操作画面で理由を確認してください" : body.last_note;
                result.attention = true;
            }
            if (goal != null && goal.Active)
            {
                result.title = goal.goal.title;
                CielConversation.GoalStep now = null;
                int done = 0, all = 0;
                foreach (var step in goal.steps ?? Array.Empty<CielConversation.GoalStep>())
                {
                    if (step == null || step.status == "skipped") continue;
                    all++;
                    if (step.status == "done") done++;
                    else if (now == null) now = step;
                }
                if (!string.IsNullOrEmpty(summary)) result.current = summary;
                else if (result.phase == "idle")
                {
                    result.heading = "シエル｜手順の開始待ち";
                    result.current = now != null ? "次の手順：" + now.label : "実行開始の通知を待っています";
                }
                if (goal.goal.status == "paused")
                {
                    result.phase = "paused";
                    result.heading = "シエル｜停止中";
                    result.attention = true;
                    result.elapsed = "";
                    result.current = string.IsNullOrEmpty(goal.attention) ? "いったん止まっています" : goal.attention;
                }
                if (now?.progress?.Length == 2 && now.progress[1] > 0)
                {
                    int total = now.progress[1], got = Math.Max(0, Math.Min(now.progress[0], total));
                    result.progress = $"現在の手順：{got} / {total}";
                    result.fraction = (float)got / total;
                }
                else if (all > 0)
                {
                    result.progress = $"手順完了：{done} / {all}";
                    result.fraction = (float)done / all;
                }
                return result;
            }
            if (result.phase == "idle" && goal != null && goal.HasGoal && recent)
            {
                result.title = goal.goal.title;
                result.heading = "シエル｜直前の目的";
                result.current = goal.goal.status == "done" ? "できた！" : goal.goal.status == "stopped" ? "やめた"
                    : string.IsNullOrEmpty(goal.attention) ? "うまくいかなかった" : goal.attention;
                result.attention = goal.goal.status == "failed";
            }
            return result;
        }
    }
}
