// 会話の画面（CielConversationUI）のうち、会話のまとめ（議事録・目標と計画・調べもののまとめ など）。
// 中身は CielConversation.Summary（会話サーバーの minutes.py が、ライブの更新・清書のたびに送る）。
// - 記録中は、参加者の札の下に 1 行の帯（いまの話題と、項目の数）。タップでパネルを開く。
// - パネル：見出しごとの項目。新しく増えた・変わった項目は数秒光る。下に「今すぐ更新」「まとめて送る」。
//   とっていないときは、直近のまとめの結果と、まとめの種類を選んで始めるボタン（左下の「まとめ」のボタンからも開く）。
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const float ItemGlowSeconds = 5f;
        static readonly Color ItemColor = new Color(0.50f, 0.91f, 1f, 0.05f);

        RectTransform _summaryStrip, _summaryContent, _summaryView, _summaryButtons;
        Text _stripText, _summaryTitle, _summaryMeta;
        GameObject _summaryPanel;
        int _summaryRevision = -1;
        string _summaryMeeting;
        float _summaryMetaAt;
        readonly Dictionary<string, int> _itemRevs = new Dictionary<string, int>();
        readonly Dictionary<string, float> _itemGlowAt = new Dictionary<string, float>();
        readonly List<(string id, Image bg)> _itemBgs = new List<(string, Image)>();

        void BuildSummary(RectTransform root)
        {
            var strip = Rect("SummaryStrip", root, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, Vector2.zero);
            strip.anchorMin = new Vector2(0, 1);
            strip.anchorMax = Vector2.one;
            _summaryStrip = strip;
            var bg = Img(strip, "circle", AmberGlass, raycast: true, child: true);
            bg.type = Image.Type.Sliced;
            bg.gameObject.AddComponent<PillRadius>();
            Edge(strip, WithAlpha(Amber, 0.6f));
            strip.gameObject.AddComponent<Button>().targetGraphic = bg;
            strip.GetComponent<Button>().onClick.AddListener(() => ShowSummary(!_summaryPanel.activeSelf));
            _stripText = Txt("Text", strip, 11, TextMain, TextAnchor.MiddleLeft);
            _stripText.supportRichText = false;
            _stripText.verticalOverflow = VerticalWrapMode.Truncate;
            Stretch(_stripText.rectTransform);
            _stripText.rectTransform.offsetMin = new Vector2(14, 0);
            _stripText.rectTransform.offsetMax = new Vector2(-14, 0);
            strip.gameObject.SetActive(false);

            var panel = Rect("SummaryPanel", root, Center, Center, Vector2.zero, Vector2.zero);
            panel.anchorMin = Vector2.zero;
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(16, 115);
            panel.offsetMax = new Vector2(-16, -96);
            Rounded(panel, SheetColor, 18, raycast: true);
            _summaryPanel = panel.gameObject;
            var close = Rect("Close", panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var closeButton = close.gameObject.AddComponent<Button>();
            closeButton.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            closeButton.onClick.AddListener(() => ShowSummary(false));
            _summaryTitle = Txt("Title", panel, 17, TextMain, TextAnchor.MiddleLeft, true);
            _summaryTitle.supportRichText = false;
            _summaryTitle.verticalOverflow = VerticalWrapMode.Truncate;
            Place(_summaryTitle.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -12), new Vector2(280, 30));
            _summaryMeta = Txt("Meta", panel, 11, TextNote, TextAnchor.MiddleLeft);
            _summaryMeta.supportRichText = false;
            Place(_summaryMeta.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -42), new Vector2(300, 18));

            var view = Rect("Viewport", panel, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(view);
            view.offsetMax = new Vector2(-14, -68);
            view.gameObject.AddComponent<RectMask2D>();
            Img(view, null, Color.clear, raycast: true);
            _summaryView = view;
            var scroll = view.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            scroll.viewport = view;
            scroll.scrollSensitivity = 35;
            _summaryContent = Rect("Content", view, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            _summaryContent.anchorMin = new Vector2(0, 1);
            _summaryContent.anchorMax = Vector2.one;
            var layout = _summaryContent.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.spacing = 8;
            layout.padding = new RectOffset(4, 4, 4, 8);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            _summaryContent.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.content = _summaryContent;

            // 記録中だけ出す下のボタン
            var buttons = Rect("Buttons", panel, new Vector2(0.5f, 0), new Vector2(0.5f, 0), Vector2.zero, Vector2.zero);
            buttons.anchorMin = new Vector2(0, 0);
            buttons.anchorMax = new Vector2(1, 0);
            buttons.offsetMin = new Vector2(14, 12);
            buttons.offsetMax = new Vector2(-14, 56);
            _summaryButtons = buttons;
            var refresh = Rect("Refresh", buttons, Center, Center, Vector2.zero, Vector2.zero);
            refresh.anchorMin = Vector2.zero;
            refresh.anchorMax = new Vector2(0.5f, 1);
            refresh.offsetMin = Vector2.zero;
            refresh.offsetMax = new Vector2(-5, 0);
            PanelButton(refresh, "今すぐ更新", TextAnchor.MiddleCenter).onClick.AddListener(() => _conversation.RefreshSummary());
            var finish = Rect("Finish", buttons, Center, Center, Vector2.zero, Vector2.zero);
            finish.anchorMin = new Vector2(0.5f, 0);
            finish.anchorMax = Vector2.one;
            finish.offsetMin = new Vector2(5, 0);
            finish.offsetMax = Vector2.zero;
            var finishButton = PanelButton(finish, "まとめて送る", TextAnchor.MiddleCenter);
            finishButton.targetGraphic.color = AmberGlass;
            finishButton.GetComponentInChildren<Text>().color = Amber;
            finishButton.onClick.AddListener(() => _conversation.FinishSummary());
            _summaryPanel.SetActive(false);
        }

        void ShowSummary(bool open)
        {
            if (open)
            {
                _researchPanel.SetActive(false);
                ShowPerson(null);
            }
            _summaryPanel.SetActive(open);
            if (open) BuildSummaryContent();
        }

        void RefreshSummary()
        {
            if (_conversation == null || _summaryStrip == null) return;
            var c = _conversation;
            var s = c.Summary;
            var recording = c.Status == CielConversation.State.Connected && s != null && s.recording;
            _summaryStrip.gameObject.SetActive(recording);
            // 参加者の札が出ていれば、その下に並べる
            var top = _peopleRow.gameObject.activeSelf ? -94f : -58f;
            _summaryStrip.offsetMin = new Vector2(16, top - 28);
            _summaryStrip.offsetMax = new Vector2(_researchButton.gameObject.activeSelf ? -152 : -16, top);
            if (recording) _stripText.text = StripText(s);
            if (_summaryRevision == c.SummaryRevision) return;
            _summaryRevision = c.SummaryRevision;
            MarkChangedItems(s);
            if (_summaryPanel.activeSelf) BuildSummaryContent();
        }

        static string StripText(CielConversation.SummaryState s)
        {
            var text = "● 記録中｜" + (string.IsNullOrEmpty(s.current_topic) ? s.label : "いまの話題：" + s.current_topic);
            var counts = new List<string>();
            foreach (var section in s.sections)
                if (section.kind != "topic" && section.items != null && section.items.Length > 0 && counts.Count < 2)
                    counts.Add($"{section.label} {section.items.Length}");
            return counts.Count > 0 ? text + "｜" + string.Join("・", counts) : text;
        }

        // 前に届いたまとめと比べて、新しく増えた・変わった項目を光らせる（まとめが変わったときの最初の中身は光らせない）
        void MarkChangedItems(CielConversation.SummaryState s)
        {
            var first = s == null || s.meeting_id != _summaryMeeting;
            if (first)
            {
                _itemRevs.Clear();
                _itemGlowAt.Clear();
                _summaryMeeting = s?.meeting_id;
            }
            if (s == null) return;
            foreach (var section in s.sections)
                foreach (var item in section.items ?? Array.Empty<CielConversation.SummaryItem>())
                {
                    if (!first && (!_itemRevs.TryGetValue(item.id, out var rev) || rev != item.rev)) _itemGlowAt[item.id] = Time.unscaledTime;
                    _itemRevs[item.id] = item.rev;
                }
        }

        void BuildSummaryContent()
        {
            foreach (Transform child in _summaryContent) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            _itemBgs.Clear();
            var c = _conversation;
            var s = c.Summary;
            var recording = s != null && s.recording;
            _summaryButtons.gameObject.SetActive(recording);
            _summaryView.offsetMin = new Vector2(14, recording ? 64 : 12);
            _summaryTitle.text = s == null ? "まとめ" : string.IsNullOrEmpty(s.title) ? s.label : s.title;
            UpdateSummaryMeta();

            if (s != null && !recording)
            {
                var stage = StageText(s.stage);
                if (stage != "") Txt("Stage", _summaryContent, 13, s.stage == "failed" ? Alert : Amber, TextAnchor.UpperLeft).text = stage;
            }
            if (s != null)
            {
                if (recording && !string.IsNullOrEmpty(s.current_topic))
                {
                    SummaryLabel("いまの話題");
                    var topic = Txt("CurrentTopic", _summaryContent, 14, TextMain, TextAnchor.UpperLeft, true);
                    topic.supportRichText = false;
                    topic.text = s.current_topic;
                }
                if (!string.IsNullOrEmpty(s.summary)) PlainText(s.summary, 12, TextSub);
                var any = false;
                foreach (var section in s.sections)
                {
                    if (section.items == null || section.items.Length == 0) continue;
                    any = true;
                    SummaryLabel($"{section.label}（{section.items.Length}）");
                    foreach (var item in section.items) BuildItem(section.kind, item);
                }
                if (!any && recording) Note(_summaryContent, "話がたまると、ここにまとめが出ます（話が続いていれば 1〜2 分ごと）。すぐ見たいときは「今すぐ更新」。");
            }
            if (!recording) BuildTemplateChoice(c);
            UpdateSummaryGlow();
        }

        void BuildTemplateChoice(CielConversation c)
        {
            SummaryLabel("まとめをとる");
            Note(_summaryContent, "とっているあいだの会話を、画面で少しずつまとめます。終えると、清書した下書きを送ります。");
            var templates = c.SummaryTemplates.Count > 0 ? c.SummaryTemplates
                : new[] { new CielConversation.SummaryTemplate { name = "meeting", label = "会議の議事録", description = "" } };
            foreach (var t in templates)
            {
                var row = Row(_summaryContent, string.IsNullOrEmpty(t.description) ? 44 : 58);
                var name = t.name;
                var b = PanelButton(row, t.label, TextAnchor.UpperLeft);
                var label = b.GetComponentInChildren<Text>();
                label.rectTransform.offsetMin = new Vector2(12, 6);
                label.rectTransform.offsetMax = new Vector2(-12, -8);
                label.fontStyle = FontStyle.Bold;
                if (!string.IsNullOrEmpty(t.description))
                {
                    var d = Txt("Description", row, 11, TextSub, TextAnchor.LowerLeft);
                    d.supportRichText = false;
                    Stretch(d.rectTransform);
                    d.rectTransform.offsetMin = new Vector2(12, 7);
                    d.rectTransform.offsetMax = new Vector2(-12, -6);
                    d.text = t.description;
                }
                b.interactable = c.Status == CielConversation.State.Connected;
                b.onClick.AddListener(() => c.StartSummary(name));
            }
        }

        static string StageText(string stage) => stage switch
        {
            "queued" or "building" => "下書きを作っています…",
            "sent" => "Discord に下書きを送りました。確かめてから共有してください。",
            "saved_locally" => "Discord に送れなかったので、下書きをサーバーに保存しました。",
            "empty" => "発言が少なかったので、まとめにしませんでした。",
            "failed" => "まとめを作れませんでした。",
            _ => "",
        };

        void BuildItem(string kind, CielConversation.SummaryItem item)
        {
            var go = new GameObject("Item", typeof(RectTransform), typeof(VerticalLayoutGroup));
            go.transform.SetParent(_summaryContent, false);
            var r = (RectTransform)go.transform;
            var layout = go.GetComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(10, 10, 7, 7);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            // 背景は子に置く（並べる大きさに画像の大きさが混ざらないように）
            var bg = Img(r, "circle", ItemColor, child: true);
            SetRadius(bg, 8);
            _itemBgs.Add((item.id, bg));

            var main = Txt("Text", r, 13, TextMain, TextAnchor.UpperLeft, kind == "topic");
            main.supportRichText = false;
            main.text = kind switch
            {
                "topic" => item.text,
                "action" => (item.done ? "■ " : "□ ") + item.text + ActionDetail(item),
                "goal" => "◎ " + item.text + (string.IsNullOrEmpty(item.status) ? "" : $"（{item.status}）"),
                "question" => "？ " + item.text,
                _ => "・" + item.text,
            };
            if (kind == "action" && item.done) main.color = TextNote;
            foreach (var p in item.points ?? Array.Empty<string>())
            {
                var point = Txt("Point", r, 12, TextSub, TextAnchor.UpperLeft);
                point.supportRichText = false;
                point.text = "・" + p;
            }
            foreach (var source in item.sources ?? Array.Empty<CielConversation.SummarySource>())
            {
                if (!CielConversation.IsWebUrl(source.url)) continue;
                var link = Txt("Source", r, 11, Cyan, TextAnchor.UpperLeft);
                link.supportRichText = false;
                link.raycastTarget = true;
                link.text = $"↗ {source.title}（{new Uri(source.url).Host}）";
                var url = source.url;
                link.gameObject.AddComponent<Button>().onClick.AddListener(() => Application.OpenURL(url));
            }
        }

        static string ActionDetail(CielConversation.SummaryItem item)
        {
            var who = string.IsNullOrEmpty(item.who) ? "" : item.who;
            var due = string.IsNullOrEmpty(item.due) ? "" : item.due + " まで";
            var detail = who != "" && due != "" ? $"{who}、{due}" : who + due;
            return (detail == "" ? "" : $"（{detail}）") + (item.done ? "（済み）" : "");
        }

        void SummaryLabel(string text)
        {
            var t = Txt("Label", _summaryContent, 13, SectionText, TextAnchor.MiddleLeft, true);
            t.text = text;
        }

        void PlainText(string text, int size, Color color)
        {
            var t = Txt("Text", _summaryContent, size, color, TextAnchor.UpperLeft);
            t.supportRichText = false;
            t.text = text;
        }

        // 「12:03〜 記録中・更新 40 秒前・まだ反映していない発言 4」（Update から 1 秒ごと）
        void UpdateSummaryMeta()
        {
            var s = _conversation.Summary;
            if (s == null) { _summaryMeta.text = ""; return; }
            var started = DateTimeOffset.FromUnixTimeMilliseconds((long)(s.started_at * 1000)).ToLocalTime();
            var parts = new List<string> { $"{s.label}・{started:HH:mm}〜" + (s.recording ? " 記録中" : "") };
            if (s.recording)
            {
                var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
                parts.Add(s.updated_at <= 0 ? "まだ更新していません" : $"更新 {Ago(now - s.updated_at)}");
                if (s.pending_turns > 0) parts.Add($"まだ反映していない発言 {s.pending_turns}");
            }
            _summaryMeta.text = string.Join("・", parts);
        }

        static string Ago(double seconds) => seconds < 60 ? $"{Math.Max(0, (int)seconds)} 秒前" : $"{(int)(seconds / 60)} 分前";

        // 新しく増えた・変わった項目を、数秒かけて光らせて戻す（Update から）
        void UpdateSummaryGlow()
        {
            foreach (var (id, bg) in _itemBgs)
            {
                var k = _itemGlowAt.TryGetValue(id, out var at) ? Mathf.Clamp01(1f - (Time.unscaledTime - at) / ItemGlowSeconds) : 0f;
                bg.color = Color.Lerp(ItemColor, new Color(0.10f, 0.45f, 0.58f, 0.65f), k);
            }
        }

        void UpdateSummary()
        {
            if (_summaryPanel == null || !_summaryPanel.activeSelf) return;
            UpdateSummaryGlow();
            if (Time.unscaledTime - _summaryMetaAt < 1f) return;
            _summaryMetaAt = Time.unscaledTime;
            UpdateSummaryMeta();
        }
    }
}
