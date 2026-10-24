// 会話の画面（CielConversationUI）のうち、調べたことと出典のパネル（右上のボタン・調べものの札で開く）。
// 中身は CielConversation.ResearchResults（会話サーバーの web_research.py が送る）。
// 1 回の調べものを 1 ページにして、下の「‹ 前」「次 ›」で送る（番号は古い順。開くと最新）。
// 最新を見ているあいだに新しい調べものが届いたら、そのページへ進む。前のページを読んでいるあいだは、そのページのまま。
using System;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        Button _researchButton;
        Text _researchLabel;
        GameObject _researchPanel;
        RectTransform _researchContent, _researchView, _researchPager;
        ScrollRect _researchScroll;
        Text _researchPage;
        int _researchRevision = -1;
        int _researchShown = -1;        // 出しているページの調べものの id
        bool _researchFollow = true;    // 最新のページを見ている（新しい調べものが届いたら進む）

        void BuildResearch(RectTransform root)
        {
            var chip = Rect("ResearchButton", root, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -52), new Vector2(124, 34));
            _researchButton = chip.gameObject.AddComponent<Button>();
            _researchButton.targetGraphic = Pill(chip, Glass, raycast: true);
            _researchLabel = Txt("Label", chip, 12, Cyan, TextAnchor.MiddleCenter);
            Stretch(_researchLabel.rectTransform);
            _researchButton.onClick.AddListener(() =>
            {
                if (_researchPanel.activeSelf) _researchPanel.SetActive(false);
                else OpenResearch(-1);
            });

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
            _researchView = view;
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
            _researchScroll = scroll;

            // ページ送り（2 ページ以上のときだけ）
            var pager = Rect("Pager", panel, new Vector2(0.5f, 0), new Vector2(0.5f, 0), Vector2.zero, Vector2.zero);
            pager.anchorMin = new Vector2(0, 0);
            pager.anchorMax = new Vector2(1, 0);
            pager.offsetMin = new Vector2(14, 12);
            pager.offsetMax = new Vector2(-14, 52);
            _researchPager = pager;
            var prev = Rect("Prev", pager, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(96, 40));
            PanelButton(prev, "‹ 前", TextAnchor.MiddleCenter).onClick.AddListener(() => TurnResearchPage(-1));
            var next = Rect("Next", pager, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(96, 40));
            PanelButton(next, "次 ›", TextAnchor.MiddleCenter).onClick.AddListener(() => TurnResearchPage(1));
            _researchPage = Txt("Page", pager, 13, TextSub, TextAnchor.MiddleCenter);
            Stretch(_researchPage.rectTransform);
            _researchPanel.SetActive(false);
            chip.gameObject.SetActive(false);
        }

        // パネルを開く。id が -1 なら最新のページ
        void OpenResearch(int id)
        {
            ShowPerson(null);
            _summaryPanel.SetActive(false);
            var results = _conversation.ResearchResults;
            if (results.Count == 0) return;
            var index = id < 0 ? -1 : IndexOfResearch(id);
            ShowResearchPage(index < 0 ? results.Count - 1 : index);
            _researchPanel.SetActive(true);
        }

        int IndexOfResearch(int id)
        {
            var results = _conversation.ResearchResults;
            for (int i = 0; i < results.Count; i++) if (results[i].id == id) return i;
            return -1;
        }

        void TurnResearchPage(int step)
        {
            var count = _conversation.ResearchResults.Count;
            var index = IndexOfResearch(_researchShown);
            if (count == 0 || index < 0) return;
            ShowResearchPage(Mathf.Clamp(index + step, 0, count - 1));
        }

        void ShowResearchPage(int index)
        {
            var results = _conversation.ResearchResults;
            _researchShown = results[index].id;
            _researchFollow = index == results.Count - 1;
            BuildResearchPage(results[index]);
            _researchScroll.verticalNormalizedPosition = 1f;   // ページの頭から
            var paged = results.Count > 1;
            _researchPager.gameObject.SetActive(paged);
            _researchView.offsetMin = new Vector2(14, paged ? 60 : 12);
            _researchPage.text = $"{index + 1} / {results.Count}";
            _researchPager.Find("Prev").GetComponent<Button>().interactable = index > 0;
            _researchPager.Find("Next").GetComponent<Button>().interactable = index < results.Count - 1;
        }

        void RefreshResearch()
        {
            if (_conversation == null || _researchRevision == _conversation.ResearchRevision) return;
            _researchRevision = _conversation.ResearchRevision;
            var results = _conversation.ResearchResults;
            _researchButton.gameObject.SetActive(results.Count > 0);
            _researchLabel.text = "調査・出典 " + results.Count;
            if (results.Count == 0)
            {
                _researchPanel.SetActive(false);
                _researchShown = -1;
                _researchFollow = true;
                return;
            }
            // 最新を見ていれば最新へ進み、前のページを読んでいれば、そのページを作り直す（届いた結果を反映する）
            var index = _researchFollow ? -1 : IndexOfResearch(_researchShown);
            ShowResearchPage(index < 0 ? results.Count - 1 : index);
        }

        void BuildResearchPage(CielConversation.ResearchResult r)
        {
            foreach (Transform child in _researchContent) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            var heading = Txt("Question", _researchContent, 15, TextMain, TextAnchor.UpperLeft, true);
            heading.supportRichText = false;
            heading.text = r.question;
            var body = Txt("Summary", _researchContent, 13, TextSub, TextAnchor.UpperLeft);
            body.supportRichText = true;
            var state = r.status == "pending" ? "調べています…" : r.status == "completed" ? MarkdownToRichText(r.Summary) : "確認できませんでした。";
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

        static readonly Regex MdHeading = new Regex(@"^(#{1,6})\s+(.*?)(\s+#+)?$");
        static readonly Regex MdRule = new Regex(@"^([-*_])(\s*\1){2,}$");
        static readonly Regex MdBullet = new Regex(@"^(\s*)[-*+]\s+(.*)$");
        static readonly Regex MdNumbered = new Regex(@"^(\s*)(\d+[.)]\s+.*)$");
        static readonly Regex MdQuote = new Regex(@"^>\s?(.*)$");
        static readonly Regex MdTableRule = new Regex(@"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$");
        static readonly Regex MdLink = new Regex(@"!?\[([^\]]*)\]\(([^()\s]|\([^()]*\))*\)");
        static readonly Regex MdCode = new Regex(@"`([^`]+)`");
        static readonly Regex MdBold = new Regex(@"\*\*(?=\S)(.+?)(?<=\S)\*\*");
        static readonly Regex MdItalic = new Regex(@"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])");
        static readonly Regex MdEscape = new Regex(@"\\([\\`*_{}\[\]()#+\-.!|>~])");

        // 調査結果のマークダウンを Text のリッチテキストにする。
        // 「<」は全角にして、Web 由来の文字列が <size> などのタグとして効かないようにする。
        internal static string MarkdownToRichText(string markdown)
        {
            var output = new StringBuilder();
            bool fence = false, blank = false;
            foreach (var raw in markdown.Replace("\r\n", "\n").Split('\n'))
            {
                var line = raw.TrimEnd().Replace("<", "＜");
                var trimmed = line.TrimStart();
                if (trimmed.StartsWith("```")) { fence = !fence; continue; }
                if (!fence)
                {
                    Match m;
                    if (MdRule.IsMatch(trimmed) || (trimmed.Contains("-") && trimmed.Contains("|") && MdTableRule.IsMatch(trimmed))) continue;
                    if ((m = MdHeading.Match(trimmed)).Success)
                        line = $"<size={(m.Groups[1].Length <= 2 ? 16 : 14)}><b>{Inline(m.Groups[2].Value)}</b></size>";
                    else if ((m = MdBullet.Match(line)).Success)
                        line = Indent(m.Groups[1].Value) + "・" + Inline(m.Groups[2].Value);
                    else if ((m = MdNumbered.Match(line)).Success)
                        line = Indent(m.Groups[1].Value) + Inline(m.Groups[2].Value);
                    else if ((m = MdQuote.Match(trimmed)).Success)
                        line = "｜" + Inline(m.Groups[1].Value);
                    else if (trimmed.Length > 1 && trimmed.StartsWith("|") && trimmed.EndsWith("|"))
                        line = string.Join(" ／ ", trimmed.Substring(1, trimmed.Length - 2).Split('|').Select(c => Inline(c.Trim())));
                    else
                        line = Inline(line);
                }
                // 空行は続けず1つにまとめる
                if (line.Length == 0) { if (blank || output.Length == 0) continue; blank = true; }
                else blank = false;
                output.Append(line).Append('\n');
            }
            return output.ToString().TrimEnd();
        }

        static string Indent(string spaces) => new string('　', spaces.Replace("\t", "  ").Length / 2);

        static string Inline(string text)
        {
            text = MdLink.Replace(text, "$1");
            text = MdCode.Replace(text, "$1");
            // 5000字で切られて閉じていない ** は記号だけ消す
            text = MdBold.Replace(text, "<b>$1</b>").Replace("**", "");
            text = MdItalic.Replace(text, "<i>$1</i>");
            return MdEscape.Replace(text, "$1");
        }
    }
}
