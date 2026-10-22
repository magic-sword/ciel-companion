// 会話の画面（CielConversationUI）のうち、参加者の札（左上、接続の状態の下）と、名前を直すパネル（札をタップで開く）。
// 中身は CielConversation.Speakers（会話サーバーの speakers.py が、聞き分けた人と最後に話した人を送る）。
// 最後に話したと判定した人の札は、しばらく光る（「たぶん」の判定は弱く光り、名前に「？」を付ける）。
// パネルでは、この会話の間だけの名前を付ける・同じ人にまとめる・さっきの発言を分けるができる（声や名前は保存しない）。
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const float SpeakingGlowSeconds = 6f;

        RectTransform _peopleRow, _peopleChips;
        GameObject _peoplePanel;
        Text _peopleTitle;
        RectTransform _peopleContent;
        string _peopleSelected, _peopleShown;
        int _peopleRevision = -1;
        readonly List<(string id, Image bg, Image edge, Text label, string name)> _chips = new List<(string, Image, Image, Text, string)>();

        void BuildPeople(RectTransform root)
        {
            // 札の列。人が多いときは横にすべらせる。右上の「調査・出典」のボタンにかからない幅にする
            var row = Rect("People", root, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, Vector2.zero);
            row.anchorMin = new Vector2(0, 1);
            row.anchorMax = Vector2.one;
            row.offsetMin = new Vector2(16, -88);
            row.offsetMax = new Vector2(-152, -58);
            row.gameObject.AddComponent<RectMask2D>();
            Img(row, null, Color.clear, raycast: true);
            var scroll = row.gameObject.AddComponent<ScrollRect>();
            scroll.vertical = false;
            scroll.viewport = row;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            _peopleRow = row;
            _peopleChips = Rect("Chips", row, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(0, 30));
            var layout = _peopleChips.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.spacing = 6;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            _peopleChips.gameObject.AddComponent<ContentSizeFitter>().horizontalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.content = _peopleChips;
            row.gameObject.SetActive(false);

            var panel = Rect("PeoplePanel", root, Center, Center, Vector2.zero, Vector2.zero);
            panel.anchorMin = Vector2.zero;
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(16, 115);
            panel.offsetMax = new Vector2(-16, -96);
            Rounded(panel, SheetColor, 18, raycast: true);
            _peoplePanel = panel.gameObject;
            var close = Rect("Close", panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var button = close.gameObject.AddComponent<Button>();
            button.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            button.onClick.AddListener(() => ShowPerson(null));
            _peopleTitle = Txt("Title", panel, 17, TextMain, TextAnchor.MiddleLeft, true);
            _peopleTitle.supportRichText = false;
            _peopleTitle.horizontalOverflow = HorizontalWrapMode.Overflow;
            Place(_peopleTitle.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -16), new Vector2(260, 30));
            var view = Rect("Viewport", panel, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(view);
            view.offsetMin = new Vector2(14, 12);
            view.offsetMax = new Vector2(-14, -58);
            view.gameObject.AddComponent<RectMask2D>();
            Img(view, null, Color.clear, raycast: true);
            var panelScroll = view.gameObject.AddComponent<ScrollRect>();
            panelScroll.horizontal = false;
            panelScroll.viewport = view;
            panelScroll.scrollSensitivity = 35;
            _peopleContent = Rect("Content", view, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            _peopleContent.anchorMin = new Vector2(0, 1);
            _peopleContent.anchorMax = Vector2.one;
            var content = _peopleContent.gameObject.AddComponent<VerticalLayoutGroup>();
            content.spacing = 10;
            content.padding = new RectOffset(4, 4, 4, 4);
            content.childControlWidth = content.childControlHeight = true;
            content.childForceExpandWidth = true;
            content.childForceExpandHeight = false;
            _peopleContent.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            panelScroll.content = _peopleContent;
            _peoplePanel.SetActive(false);
        }

        void RefreshPeople()
        {
            if (_conversation == null || _peopleRow == null) return;
            var c = _conversation;
            _peopleRow.gameObject.SetActive(c.Status == CielConversation.State.Connected && c.Speakers.Count > 0);
            // 右上の「調査・出典」のボタンが出ていなければ、右端まで使う
            _peopleRow.offsetMax = new Vector2(_researchButton.gameObject.activeSelf ? -152 : -16, -58);
            if (_peopleRevision == c.SpeakersRevision) return;
            _peopleRevision = c.SpeakersRevision;
            foreach (Transform child in _peopleChips) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            _chips.Clear();
            var icon = Rect("Icon", _peopleChips, Center, Center, Vector2.zero, Vector2.zero);
            icon.gameObject.AddComponent<LayoutElement>().preferredWidth = 18;
            Icon(icon, "people", 15, WithAlpha(Cyan, 0.8f));
            foreach (var s in c.Speakers) BuildChip(s);
            UpdatePeople();
            // 開いているパネルは、中身が変わったときだけ作り直す（話すたびに作り直すと、入れかけの名前が消える）
            if (_peopleSelected != null && PanelKey(_peopleSelected) != _peopleShown) ShowPerson(_peopleSelected);
        }

        void BuildChip(CielConversation.Speaker s)
        {
            var chip = new GameObject("Person", typeof(RectTransform), typeof(LayoutElement));
            chip.transform.SetParent(_peopleChips, false);
            var r = (RectTransform)chip.transform;
            chip.GetComponent<LayoutElement>().preferredHeight = 28;
            // 背景は子に置く（札に Image があると、画像の大きさが札の幅として並べ方に伝わる）
            var bg = Img(r, "circle", Glass, raycast: true, child: true);
            bg.type = Image.Type.Sliced;
            bg.gameObject.AddComponent<PillRadius>();
            var edge = Edge(r, WithAlpha(Cyan, 0.25f));
            var layout = chip.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(10, 12, 0, 0);
            layout.spacing = 6;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            // 点の色：声を覚えている人（ミント）・この会話で名前を聞いた人（シアン）・まだ名前を知らない人（灰）
            var dot = new GameObject("Dot", typeof(RectTransform), typeof(LayoutElement));
            dot.transform.SetParent(r, false);
            var dotLayout = dot.GetComponent<LayoutElement>();
            dotLayout.preferredWidth = dotLayout.preferredHeight = 7;
            Img((RectTransform)dot.transform, "circle", s.remembered ? Mint : s.named ? Cyan : Idle);
            var label = Txt("Name", r, 12, s.named || s.remembered ? TextMain : TextNote, TextAnchor.MiddleLeft);
            label.supportRichText = false;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            label.text = s.name;
            var button = chip.AddComponent<Button>();
            button.targetGraphic = bg;
            var id = s.id;
            button.onClick.AddListener(() => ShowPerson(_peopleSelected == id ? null : id));
            _chips.Add((id, bg, edge, label, s.name));
        }

        // 最後に話した人の札を光らせ、だんだん戻す（Update から）
        void UpdatePeople()
        {
            if (_chips.Count == 0) return;
            var c = _conversation;
            foreach (var (id, bg, edge, label, name) in _chips)
            {
                var speaking = id == c.SpeakingId && c.SpeakingAt >= 0f;
                var k = speaking ? Mathf.Clamp01(1f - (Time.unscaledTime - c.SpeakingAt) / SpeakingGlowSeconds) : 0f;
                if (!c.SpeakingSure) k *= 0.5f;
                edge.color = WithAlpha(Cyan, 0.25f + 0.75f * k);
                bg.color = Color.Lerp(Glass, new Color(0.10f, 0.45f, 0.58f, 0.65f), k);
                var text = speaking && !c.SpeakingSure ? name + "？" : name;
                if (label.text != text) label.text = text;
            }
        }

        // 札をタップしたときのパネル。id が null なら閉じる
        void ShowPerson(string id)
        {
            var person = id == null ? null : FindSpeaker(id);
            _peopleSelected = person?.id;
            _peopleShown = person == null ? null : PanelKey(person.id);
            _peoplePanel.SetActive(person != null);
            if (person == null) return;
            _researchPanel.SetActive(false);
            foreach (Transform child in _peopleContent) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            _peopleTitle.text = person.name;
            var c = _conversation;

            Note(_peopleContent, person.remembered
                ? "シエルが声を覚えている人です。名前を変えるときは、ご本人がシエルに頼んでください。"
                : person.named
                    ? "この会話の間だけの名前です（声や名前は保存しません）。"
                    : "まだ名前を知らない人です。名前を付けると、シエルもその名前で呼びます（この会話の間だけ）。");

            if (!person.remembered)
            {
                PanelLabel(person.named ? "名前を直す" : "名前を付ける");
                var row = Row(_peopleContent, 40);
                var field = Rect("NameField", row, Center, Center, Vector2.zero, Vector2.zero);
                Stretch(field);
                field.offsetMax = new Vector2(-80, 0);
                Rounded(field, new Color(1f, 1f, 1f, 0.08f), 8, raycast: true);
                var text = Txt("Text", field, 14, TextMain, TextAnchor.MiddleLeft);
                text.supportRichText = false;
                Stretch(text.rectTransform);
                text.rectTransform.offsetMin = new Vector2(10, 0);
                text.rectTransform.offsetMax = new Vector2(-10, 0);
                var placeholder = Txt("Placeholder", field, 14, TextNote, TextAnchor.MiddleLeft);
                placeholder.text = "名前を入れる";
                Stretch(placeholder.rectTransform);
                placeholder.rectTransform.offsetMin = text.rectTransform.offsetMin;
                placeholder.rectTransform.offsetMax = text.rectTransform.offsetMax;
                var input = field.gameObject.AddComponent<InputField>();
                input.textComponent = text;
                input.placeholder = placeholder;
                input.characterLimit = 40;
                input.lineType = InputField.LineType.SingleLine;
                input.text = person.named ? person.name : "";
                var warning = Txt("Warning", _peopleContent, 11, Amber, TextAnchor.UpperLeft);
                warning.gameObject.SetActive(false);
                var ok = Rect("Set", row, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(72, 40));
                var okButton = PanelButton(ok, "決める", TextAnchor.MiddleCenter);
                var target = person.id;
                okButton.onClick.AddListener(() =>
                {
                    var name = input.text.Trim();
                    if (name.Length == 0) return;
                    var same = FindSpeakerByName(name, target);
                    if (same != null)
                    {
                        // 会話サーバーも同じ名前は断る（name_taken）。同じ人なら、まとめてもらう
                        warning.text = $"「{same.name}」はもういます。同じ人なら、下の「同じ人」を使ってください。";
                        warning.gameObject.SetActive(true);
                        return;
                    }
                    c.FixSpeaker("name", target, name: name);
                    ShowPerson(null);
                });
            }

            var others = new List<CielConversation.Speaker>();
            foreach (var s in c.Speakers)
                if (s.id != person.id && !(s.remembered && person.remembered)) others.Add(s);
            if (others.Count > 0)
            {
                PanelLabel("同じ人をまとめる");
                Note(_peopleContent, "シエルが同じ人を別の人として聞き分けていたら、まとめます。");
                foreach (var other in others)
                {
                    var target = other.id;
                    var b = PanelButton(Row(_peopleContent, 40), $"{other.name}{(other.named || other.remembered ? "さん" : "")}と同じ人", TextAnchor.MiddleLeft);
                    b.onClick.AddListener(() => { c.FixSpeaker("merge", person.id, into: target); ShowPerson(null); });
                }
            }

            if (c.CorrectableId == person.id)
            {
                PanelLabel("人違い");
                Note(_peopleContent, "シエルへのさっきの発言だけを、別の人の発言として分けます。");
                var b = PanelButton(Row(_peopleContent, 40), $"さっきの発言は{person.name}さんではない", TextAnchor.MiddleLeft);
                b.onClick.AddListener(() => { c.FixSpeaker("split", person.id); ShowPerson(null); });
            }
        }

        // パネルの中身を決めるもの（名簿の名前と種類、人違いを分けられる人）
        string PanelKey(string id)
        {
            var key = new System.Text.StringBuilder(_conversation.CorrectableId == id ? "c" : "-");
            foreach (var s in _conversation.Speakers) key.Append('|').Append(s.id).Append(s.name).Append(s.named).Append(s.remembered);
            return FindSpeaker(id) == null ? null : key.ToString();
        }

        CielConversation.Speaker FindSpeaker(string id)
        {
            foreach (var s in _conversation.Speakers) if (s.id == id) return s;
            return null;
        }

        CielConversation.Speaker FindSpeakerByName(string name, string except)
        {
            name = PlainName(name);
            foreach (var s in _conversation.Speakers) if (s.id != except && PlainName(s.name) == name) return s;
            return null;
        }

        // 会話サーバーの plain_name と同じ：敬称を外す
        static string PlainName(string name)
        {
            name = name.Trim();
            foreach (var suffix in new[] { "さん", "ちゃん", "くん", "君", "様" })
                if (name.EndsWith(suffix) && name.Length > suffix.Length) return name.Substring(0, name.Length - suffix.Length).Trim();
            return name;
        }

        void PanelLabel(string text)
        {
            var t = Txt("Label", _peopleContent, 13, SectionText, TextAnchor.MiddleLeft, true);
            t.text = text;
        }

        Button PanelButton(RectTransform r, string text, TextAnchor align)
        {
            var b = r.gameObject.AddComponent<Button>();
            b.targetGraphic = Rounded(r, WithAlpha(CyanDeep, 0.16f), 8, raycast: true);
            var label = Txt("Label", r, 13, Cyan, align);
            label.supportRichText = false;
            label.verticalOverflow = VerticalWrapMode.Truncate;
            label.text = text;
            Stretch(label.rectTransform);
            label.rectTransform.offsetMin = new Vector2(12, 0);
            label.rectTransform.offsetMax = new Vector2(-12, 0);
            return b;
        }
    }
}
