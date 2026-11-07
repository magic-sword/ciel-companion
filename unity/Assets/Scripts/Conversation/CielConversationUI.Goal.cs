// 会話の画面（CielConversationUI）のうち、シエルの今の目的（docs/goal-runner-design-ja.md の 4 章）。中身は CielConversation.Goal
// （会話サーバーの goals.py が送る goal.state）。ゲームを問わない形なので、label・status・progress だけで描く。
// - 操作用の画面：裏で進んでいる仕事の札の列に「目的：石のツルハシ 2/4」の札。タップで詳しいパネル（段・直したこと・あとで・
//   止まっている理由・「止める」「続ける」）。
// 配信用の映像への札は CielConversationUI.BroadcastOutput.cs が扱う。
// - 目的ができた・やめたときは、札を少しのあいだ「できた！」「やめた」で見せて消す。
using System.Text;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const float GoalEndShown = 8f;     // できた・やめたを見せておく秒数
        static readonly Color GoalGlass = new Color(0.05f, 0.22f, 0.36f, 0.72f);

        (GameObject go, Text label, Image dot) _goalTask;
        GameObject _goalPanel;
        Text _goalPanelTitle, _goalPanelBody;
        GameObject _goalStop, _goalResume;
        object _goalShown;                 // パネルに出している goal.state（変わったら書き直す）
        // 札の列（BuildTasks のあと）・パネル・配信用の札
        void BuildGoal(RectTransform root)
        {
            _goalTask = TaskChip("Goal", GoalGlass, Cyan, () => _goalPanel.SetActive(!_goalPanel.activeSelf));

            var panel = Rect("GoalPanel", root, Center, Center, Vector2.zero, Vector2.zero);
            panel.anchorMin = Vector2.zero;
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(16, 115);
            panel.offsetMax = new Vector2(-16, -96);
            Rounded(panel, SheetColor, 18, raycast: true);
            _goalPanel = panel.gameObject;
            var close = Rect("Close", panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var closeButton = close.gameObject.AddComponent<Button>();
            closeButton.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            closeButton.onClick.AddListener(() => _goalPanel.SetActive(false));
            _goalPanelTitle = Txt("Title", panel, 17, TextMain, TextAnchor.MiddleLeft, true);
            _goalPanelTitle.horizontalOverflow = HorizontalWrapMode.Overflow;
            Place(_goalPanelTitle.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -16), new Vector2(280, 30));
            _goalPanelBody = Txt("Body", panel, 14, TextSub, TextAnchor.UpperLeft);
            _goalPanelBody.supportRichText = true;
            Stretch(_goalPanelBody.rectTransform);
            _goalPanelBody.rectTransform.offsetMin = new Vector2(18, 64);
            _goalPanelBody.rectTransform.offsetMax = new Vector2(-18, -56);
            var stop = Rect("Stop", panel, new Vector2(0, 0), new Vector2(0, 0), new Vector2(16, 14), new Vector2(120, 38));
            PanelButton(stop, "止める", TextAnchor.MiddleCenter).onClick.AddListener(() => _conversation.SendGoalControl("stop"));
            _goalStop = stop.gameObject;
            var resume = Rect("Resume", panel, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-16, 14), new Vector2(120, 38));
            PanelButton(resume, "続ける", TextAnchor.MiddleCenter).onClick.AddListener(() => _conversation.SendGoalControl("resume"));
            _goalResume = resume.gameObject;
            _goalPanel.SetActive(false);

        }

        // 毎フレーム（UpdateTasks から）：札の出し入れ・中身が変わったら書き直す
        void UpdateGoal(bool connected)
        {
            var c = _conversation;
            var g = connected ? c.Goal : null;
            var recent = g != null && g.HasGoal && Time.unscaledTime - c.GoalSince < GoalEndShown;
            var show = g != null && (g.Active || recent);
            SetTask(_goalTask, show, show ? ChipText(g) : "");
            if (show) _goalTask.dot.color = WithAlpha(g.goal.status == "paused" ? Amber : Cyan,
                0.45f + 0.55f * (Mathf.Sin(Time.unscaledTime * Mathf.PI * 2 / 1.4f) + 1) / 2);
            if (!show && _goalPanel.activeSelf && (g == null || !g.HasGoal)) _goalPanel.SetActive(false);
            if (!ReferenceEquals(_goalShown, g))
            {
                _goalShown = g;
                FillGoalPanel(g);
            }

        }

        static (int done, int all, CielConversation.GoalStep now) Count(CielConversation.GoalState g)
        {
            int done = 0;
            CielConversation.GoalStep now = null;
            foreach (var s in g.steps ?? new CielConversation.GoalStep[0])
            {
                if (s.status == "done") done++;
                else if (now == null && s.status != "skipped") now = s;
            }
            return (done, g.steps?.Length ?? 0, now);
        }

        static string Progress(CielConversation.GoalStep s) =>
            s.progress != null && s.progress.Length == 2 ? $" {s.progress[0]}/{s.progress[1]}" : "";

        static string ChipText(CielConversation.GoalState g)
        {
            var st = g.goal.status;
            if (st == "done") return $"目的：{g.goal.title} できた！";
            if (st == "stopped") return $"目的：{g.goal.title}（やめた）";
            if (st == "failed") return $"目的：{g.goal.title}（できなかった）";
            var (done, all, _) = Count(g);
            return $"目的：{g.goal.title} {done}/{all}{(st == "paused" ? "・止まっている" : "")}";
        }

        static string Mark(string status) => status switch
        {
            "done" => "<color=#5BF0C8>●</color>",
            "running" => "<color=#FFC46B>▶</color>",
            "failed" => "<color=#FF9A8A>×</color>",
            "skipped" => "<color=#8FB3C3>－</color>",
            _ => "<color=#8FB3C3>○</color>",
        };

        static string Esc(string s) => (s ?? "").Replace("<", "＜").Replace(">", "＞");

        void FillGoalPanel(CielConversation.GoalState g)
        {
            if (g == null || !g.HasGoal)
            {
                _goalPanelTitle.text = "いまの目的";
                _goalPanelBody.text = "いまは目的がありません";
                _goalStop.SetActive(false);
                _goalResume.SetActive(false);
                return;
            }
            _goalPanelTitle.text = $"いまの目的・{Esc(g.goal.game_label)}";
            var b = new StringBuilder();
            b.Append($"<b>{Esc(g.goal.title)}</b>\n<color=#8FB3C3>{Esc(g.goal.by_label)}");
            if (!string.IsNullOrEmpty(g.goal.why)) b.Append($"・{Esc(g.goal.why)}");
            b.Append("</color>\n");
            if (g.SubPath != null) b.Append($"<color=#9FDDF0>› 先に：{Esc(g.SubPath)}</color>\n");
            b.Append("\n");
            foreach (var s in g.steps ?? new CielConversation.GoalStep[0]) b.Append($"{Mark(s.status)} {Esc(s.label)}{Progress(s)}\n");
            if (!string.IsNullOrEmpty(g.attention)) b.Append($"\n<color=#FFC46B>止まっている：{Esc(g.attention)}</color>\n");
            if (g.changes != null && g.changes.Length > 0)
            {
                b.Append("\n<color=#9FDDF0>直したこと</color>\n");
                foreach (var ch in g.changes) b.Append($"・{Esc(ch)}\n");
            }
            if (g.next != null && g.next.Length > 0) b.Append($"\n<color=#9FDDF0>あとで</color>\n・{Esc(string.Join("\n・", g.next))}\n");
            _goalPanelBody.text = b.ToString();
            _goalStop.SetActive(g.Active);
            _goalResume.SetActive(g.goal.status == "paused");
        }

        // 配信用の札：見出し・目的・段（5 つまで。多ければ済んだ段をたたむ）・直したこと（最後の 1 つ）・つぎ

    }
}
