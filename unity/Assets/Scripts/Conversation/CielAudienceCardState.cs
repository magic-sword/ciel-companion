// 視聴者向けの要約。受信済みの目的・状態だけを使い、内部ログや頼んだ人の名前は出さない。
using System;

namespace Ciel.Conversation
{
    public sealed class CielAudienceCardState
    {
        public bool visible, attention;
        public string heading = "シエルの目的", title = "", current = "", progress = "";
        public float fraction = -1;

        public static CielAudienceCardState From(CielConversation.GoalState goal,
            CielConversation.ActivityState activity, bool connected, bool recent)
        {
            var result = new CielAudienceCardState();
            if (!connected) return result;
            string work = null;
            if (activity?.tasks?.Length > 0) work = activity.tasks[0].title;
            if (string.IsNullOrEmpty(work)) work = activity?.doing;
            if (string.IsNullOrEmpty(work)) work = activity?.goal_step;
            if (string.IsNullOrEmpty(work) && activity?.calls?.Length > 0) work = activity.calls[0].label + "の結果を待っている";

            if (goal != null && goal.Active)
            {
                result.visible = true;
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
                result.current = !string.IsNullOrEmpty(work) ? work : now?.label ?? "準備している";
                if (goal.goal.status == "paused")
                {
                    result.attention = true;
                    result.current = string.IsNullOrEmpty(goal.attention) ? "いったん止まっている" : goal.attention;
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

            if (!string.IsNullOrEmpty(work))
            {
                result.visible = true;
                result.heading = "いまのシエル";
                result.title = work;
                result.current = "作業を進めている";
                return result;
            }
            if (goal != null && goal.HasGoal && recent)
            {
                result.visible = true;
                result.title = goal.goal.title;
                result.current = goal.goal.status == "done" ? "できた！" : goal.goal.status == "stopped" ? "やめた"
                    : string.IsNullOrEmpty(goal.attention) ? "うまくいかなかった" : goal.attention;
                result.attention = goal.goal.status == "failed";
                return result;
            }
            if (activity?.mind == "thinking" || activity?.mind == "speaking")
            {
                result.visible = true;
                result.heading = "いまのシエル";
                result.title = activity.mind == "thinking" ? "考えている" : "話している";
            }
            return result;
        }
    }
}
