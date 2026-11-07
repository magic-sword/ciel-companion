// 配信版だけの操作画面。会話の状態と既存の操作部品を使い、音声や接続を増やさない。
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        Text _broadcastGoal, _broadcastActivity;
        float _broadcastFilledAt = -1f;
        RectTransform _broadcastMonitor, _broadcastNoticeRect;
        Text _broadcastNoticeTitle, _broadcastNoticeDetail, _broadcastNoticeButtonText;
        Image _broadcastNoticeFill;
        Button _broadcastNoticeButton;
        CielBroadcastNotice _broadcastNotice;

        void BuildBroadcastSurface(RectTransform root)
        {
            var surface = Rect("BroadcastSurface", root, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(surface);
            Img(surface, null, new Color(0.025f, 0.07f, 0.11f, 1f));
        }

        void BuildBroadcastMonitor(RectTransform root)
        {
            var monitor = Rect("BroadcastMonitor", root, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            _broadcastMonitor = monitor;
            Stretch(monitor);
            monitor.offsetMin = new Vector2(20, 255);
            monitor.offsetMax = new Vector2(-20, -95);
            monitor.SetAsFirstSibling();   // 調べものなどのパネルは、この上に開く
            _broadcastGoal = BroadcastColumn(monitor, "Goal", "目的と進み具合", 0f, 0.49f);
            _broadcastActivity = BroadcastColumn(monitor, "Activity", "現在の処理", 0.51f, 1f);
            BuildBroadcastNotice(root);
        }

        void BuildBroadcastNotice(RectTransform root)
        {
            var panel = Rect("ConnectionNotice", root, Vector2.up, Vector2.up, Vector2.zero, Vector2.zero);
            panel.anchorMin = new Vector2(0, 1);
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(20, -170);
            panel.offsetMax = new Vector2(-20, -78);
            panel.SetAsFirstSibling();
            _broadcastNoticeRect = panel;
            _broadcastNoticeFill = Rounded(panel, AmberGlass, 12);
            _broadcastNoticeTitle = Txt("Title", panel, 16, Amber, TextAnchor.UpperLeft, true);
            _broadcastNoticeDetail = Txt("Detail", panel, 12, TextMain, TextAnchor.UpperLeft);
            foreach (var text in new[] { _broadcastNoticeTitle, _broadcastNoticeDetail })
            {
                text.supportRichText = false;
                text.rectTransform.anchorMin = Vector2.zero;
                text.rectTransform.anchorMax = Vector2.one;
                text.rectTransform.offsetMin = new Vector2(16, 10);
                text.rectTransform.offsetMax = new Vector2(-200, -10);
            }
            _broadcastNoticeTitle.rectTransform.offsetMin = new Vector2(16, 56);
            _broadcastNoticeDetail.rectTransform.offsetMax = new Vector2(-200, -36);
            var action = Rect("Action", panel, new Vector2(1, .5f), new Vector2(1, .5f), new Vector2(-16, 0), new Vector2(162, 40));
            _broadcastNoticeButton = PanelButton(action, "接続を再試行", TextAnchor.MiddleCenter);
            _broadcastNoticeButtonText = action.GetComponentInChildren<Text>();
            _broadcastNoticeButton.onClick.AddListener(() =>
            {
                switch (_broadcastNotice?.action)
                {
                    case CielBroadcastNotice.Action.RetryGame: _conversation.RetryGameConnection(); break;
                    case CielBroadcastNotice.Action.Connect: _conversation.StartConversation(); break;
                    case CielBroadcastNotice.Action.Reconnect: _conversation.Reconnect(); break;
                    case CielBroadcastNotice.Action.Settings:
                        OpenSheet(true);
                        int page = _pages.FindIndex(p => p.name == "Page_そのほか");
                        if (page >= 0) ShowPage(page);
                        break;
                }
                _broadcastFilledAt = -1;
                UpdateBroadcastMonitor();
            });
            panel.gameObject.SetActive(false);
        }

        void UpdateBroadcastNotice()
        {
            _broadcastNotice = CielBroadcastNotice.From(_conversation);
            bool show = _broadcastNotice.Visible;
            _broadcastNoticeRect.gameObject.SetActive(show);
            _broadcastMonitor.offsetMax = new Vector2(-20, show ? -185 : -95);
            if (!show) return;
            _broadcastNoticeTitle.text = _broadcastNotice.title;
            _broadcastNoticeDetail.text = _broadcastNotice.detail;
            _broadcastNoticeTitle.color = _broadcastNotice.error ? Alert : Amber;
            _broadcastNoticeFill.color = _broadcastNotice.error ? new Color(.36f, .07f, .08f, .95f) : AmberGlass;
            _broadcastNoticeButton.gameObject.SetActive(_broadcastNotice.action != CielBroadcastNotice.Action.None);
            _broadcastNoticeButtonText.text = _broadcastNotice.button;
        }

        Text BroadcastColumn(RectTransform root, string name, string title, float left, float right)
        {
            var column = Rect(name, root, new Vector2(left, 0), new Vector2(right, 1), Vector2.zero, Vector2.zero);
            column.anchorMin = new Vector2(left, 0);
            column.anchorMax = new Vector2(right, 1);
            column.offsetMin = column.offsetMax = Vector2.zero;
            Rounded(column, Glass, 12);
            var heading = Txt("Title", column, 16, TextMain, TextAnchor.UpperLeft, true);
            heading.text = title;
            heading.rectTransform.anchorMin = new Vector2(0, 1);
            heading.rectTransform.anchorMax = new Vector2(1, 1);
            heading.rectTransform.pivot = new Vector2(0.5f, 1);
            heading.rectTransform.anchoredPosition = new Vector2(0, -12);
            heading.rectTransform.sizeDelta = new Vector2(-32, 30);
            var view = Rect("Viewport", column, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Stretch(view);
            view.offsetMin = new Vector2(16, 14);
            view.offsetMax = new Vector2(-16, -48);
            view.gameObject.AddComponent<RectMask2D>();
            Img(view, null, Color.clear, raycast: true);
            var text = Txt("Body", view, 14, TextSub, TextAnchor.UpperLeft);
            text.supportRichText = true;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            var rect = text.rectTransform;
            rect.anchorMin = new Vector2(0, 1);
            rect.anchorMax = new Vector2(1, 1);
            rect.pivot = new Vector2(0.5f, 1);
            rect.anchoredPosition = Vector2.zero;
            rect.sizeDelta = Vector2.zero;
            text.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            var scroll = view.gameObject.AddComponent<ScrollRect>();
            scroll.viewport = view;
            scroll.content = rect;
            scroll.horizontal = false;
            scroll.scrollSensitivity = 30;
            return text;
        }

        void UpdateBroadcastMonitor()
        {
            if (_broadcastGoal == null || Time.unscaledTime - _broadcastFilledAt < 0.5f) return;
            _broadcastFilledAt = Time.unscaledTime;
            UpdateBroadcastNotice();
            var connected = _conversation.Status == CielConversation.State.Connected;
            var goal = connected ? _conversation.Goal : null;
            _broadcastGoal.text = goal != null && goal.HasGoal ? _goalPanelTitle.text + "\n\n" + _goalPanelBody.text
                : "いまは目的がありません\n\n探索や採集などの直接の作業は、右の「現在の処理」に表示します。";
            var activity = connected ? _conversation.Activity : null;
            _broadcastActivity.text = activity != null ? ActivityText(_conversation, activity)
                : connected ? "処理状態の通知を待っています" : "会話に接続していません";
        }
    }
}
