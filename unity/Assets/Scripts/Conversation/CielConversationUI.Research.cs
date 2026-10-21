// 会話の画面（CielConversationUI）のうち、調べたことと出典のパネル（右上のボタンで開く）。
// 中身は CielConversation.ResearchResults（会話サーバーの web_research.py が送る）。
using System;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        Button _researchButton;
        Text _researchLabel;
        GameObject _researchPanel;
        RectTransform _researchContent;
        int _researchRevision = -1;

        void BuildResearch(RectTransform root)
        {
            var chip = Rect("ResearchButton", root, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -52), new Vector2(124, 34));
            _researchButton = chip.gameObject.AddComponent<Button>();
            _researchButton.targetGraphic = Pill(chip, Glass, raycast: true);
            _researchLabel = Txt("Label", chip, 12, Cyan, TextAnchor.MiddleCenter);
            Stretch(_researchLabel.rectTransform);
            _researchButton.onClick.AddListener(() => _researchPanel.SetActive(!_researchPanel.activeSelf));

            var panel = Rect("ResearchPanel", root, Center, Center, Vector2.zero, Vector2.zero);
            panel.anchorMin = Vector2.zero;
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(16, 115);
            panel.offsetMax = new Vector2(-16, -96);
            Rounded(panel, SheetColor, 18, raycast: true);
            _researchPanel = panel.gameObject;
            var close = Rect("Close", panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var button = close.gameObject.AddComponent<Button>();
            button.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            button.onClick.AddListener(() => _researchPanel.SetActive(false));
            var title = Txt("Title", panel, 17, TextMain, TextAnchor.MiddleLeft, true);
            title.text = "調べたこと・出典";
            Place(title.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -16), new Vector2(240, 30));
            var view = Rect("Viewport", panel, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(view);
            view.offsetMin = new Vector2(14, 12);
            view.offsetMax = new Vector2(-14, -58);
            view.gameObject.AddComponent<RectMask2D>();
            Img(view, null, Color.clear, raycast: true);
            var scroll = view.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            scroll.viewport = view;
            scroll.scrollSensitivity = 35;
            _researchContent = Rect("Content", view, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            _researchContent.anchorMin = new Vector2(0, 1);
            _researchContent.anchorMax = Vector2.one;
            var layout = _researchContent.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.spacing = 12;
            layout.padding = new RectOffset(4, 4, 4, 4);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            _researchContent.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.content = _researchContent;
            _researchPanel.SetActive(false);
            chip.gameObject.SetActive(false);
        }

        void RefreshResearch()
        {
            if (_conversation == null || _researchRevision == _conversation.ResearchRevision) return;
            _researchRevision = _conversation.ResearchRevision;
            var results = _conversation.ResearchResults;
            _researchButton.gameObject.SetActive(results.Count > 0);
            _researchLabel.text = "調査・出典 " + results.Count;
            if (results.Count == 0) _researchPanel.SetActive(false);
            foreach (Transform child in _researchContent) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            for (int i = results.Count - 1; i >= 0; i--)
            {
                var r = results[i];
                var heading = Txt("Question", _researchContent, 15, TextMain, TextAnchor.UpperLeft, true);
                heading.supportRichText = false;
                heading.text = r.question;
                var body = Txt("Summary", _researchContent, 13, TextSub, TextAnchor.UpperLeft);
                body.supportRichText = false;
                var state = r.status == "pending" ? "調べています…" : r.status == "completed" ? r.Summary : "確認できませんでした。";
                body.text = (r.checkedAt != null ? "取得日時：" + r.checkedAt + "\n" : "") + state + (r.clipped ? "\n（一部省略）" : "");
                foreach (var source in r.sources)
                {
                    var row = Row(_researchContent, 58);
                    var link = row.gameObject.AddComponent<Button>();
                    link.targetGraphic = Rounded(row, Glass, 8, raycast: true);
                    var label = Txt("Source", row, 12, Cyan, TextAnchor.MiddleLeft);
                    label.supportRichText = false;
                    label.verticalOverflow = VerticalWrapMode.Truncate;
                    label.text = $"[{source.number}] {source.title}\n{new Uri(source.url).Host} ↗";
                    Stretch(label.rectTransform);
                    label.rectTransform.offsetMin = new Vector2(8, 4);
                    label.rectTransform.offsetMax = new Vector2(-8, -4);
                    var url = source.url;
                    link.onClick.AddListener(() => { if (CielConversation.IsWebUrl(url)) Application.OpenURL(url); });
                }
            }
        }
    }
}
