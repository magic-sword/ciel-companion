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
        CielConversation.GoalState _goalControlsTarget;
        float _goalFilled = -1; // 鮮度と残り予算を定期更新する
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
            PanelButton(stop, "止める", TextAnchor.MiddleCenter).onClick.AddListener(() => _conversation.SendGoalControl("stop", _goalControlsTarget));
            _goalStop = stop.gameObject;
            var resume = Rect("Resume", panel, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-16, 14), new Vector2(120, 38));
            PanelButton(resume, "再試行する", TextAnchor.MiddleCenter).onClick.AddListener(() => _conversation.SendGoalControl("retry", _goalControlsTarget));
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
            var view = CielWorkPresentation.From(g);
            if (show) _goalTask.dot.color = view.attention ? Amber : Cyan;
            if (!show && _goalPanel.activeSelf && (g == null || !g.HasGoal)) _goalPanel.SetActive(false);
            if (Time.unscaledTime - _goalFilled > .25f)
            {
                _goalFilled = Time.unscaledTime;
                FillGoalPanel(g);
            }
        }

        static string ChipText(CielConversation.GoalState g)
        {
            var view = CielWorkPresentation.From(g);
            return $"作業：{view.title}・{view.status}";
        }

        static string Esc(string s) => (s ?? "").Replace("<", "＜").Replace(">", "＞");

        void FillGoalPanel(CielConversation.GoalState g)
        {
            var view = CielWorkPresentation.From(g);
            _goalControlsTarget = g;
            _goalPanelTitle.text = "作業・" + Esc(g?.task?.service_label ?? "状態確認");
            _goalPanelBody.text = view.visible ? Esc(view.Summary) : "いまは作業がありません";
            _goalStop.SetActive(view.canStop);
            _goalResume.SetActive(view.canRetry);
        }
    }
}
