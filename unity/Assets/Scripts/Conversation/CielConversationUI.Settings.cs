// 会話の画面（CielConversationUI）のうち、設定画面（下からすべり出る）。
// タブ：声と会話（シエルの声の大きさ・おしゃべり度・その場にいる人）、背景（CielBackground）、
// そのほか（PC ではマイクとスピーカー、開発：開発用のサーバーにつなぐ・表情の確認ボタン）。
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        GameObject _sheetRoot;
        RectTransform _sheet;
        CanvasGroup _sheetGroup;
        float _sheetT;
        bool _sheetOpen;
        Slider _sheetSlider;
        Text _sheetValue;
        readonly List<(string key, Image edge, GameObject check, Text label)> _bgCells = new List<(string, Image, GameObject, Text)>();
        readonly List<(Image fill, Image edge, Text label)> _talkSegs = new List<(Image, Image, Text)>();
        readonly List<(Image fill, Image edge, Text label)> _presenceSegs = new List<(Image, Image, Text)>();
        Text _talkNote, _presenceNow, _presenceNote;
        GameObject _devicesSection;
        Dropdown _devices, _speakers;
        readonly List<string> _deviceGuids = new List<string>();
        readonly List<string> _speakerGuids = new List<string>();
        Image _exprSwitch, _exprKnob, _devServerSwitch, _devServerKnob;

        void BuildSheet(RectTransform root)
        {
            _sheetRoot = new GameObject("Settings", typeof(RectTransform), typeof(CanvasGroup));
            var sr = (RectTransform)_sheetRoot.transform;
            sr.SetParent(root, false);
            Stretch(sr);
            _sheetGroup = _sheetRoot.GetComponent<CanvasGroup>();
            // 外を押したら閉じる。設定画面の親ではなく兄弟に置く（親に置くと、設定画面のどこを押しても閉じてしまう）
            var dimRect = Rect("Dim", sr, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(dimRect);
            var dim = Img(dimRect, null, new Color(0.01f, 0.04f, 0.07f, 0.55f), raycast: true);
            dim.gameObject.AddComponent<Button>().onClick.AddListener(() => OpenSheet(false));

            _sheet = Rect("Sheet", sr, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            _sheet.anchorMin = Vector2.zero;
            _sheet.anchorMax = Vector2.one;
            _sheet.offsetMin = new Vector2(0, -40);   // 下の角は画面の外へ出す
            _sheet.offsetMax = new Vector2(0, -132);
            Rounded(_sheet, SheetColor, 30, raycast: true);
            var edge = Img(_sheet, "circle_outline", WithAlpha(Cyan, 0.6f), child: true);
            SetRadius(edge, 30);

            // 見出し
            var head = Rect("Head", _sheet, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, 0), Vector2.zero);
            head.anchorMin = new Vector2(0, 1);
            head.anchorMax = new Vector2(1, 1);
            head.offsetMin = new Vector2(22, -68);
            head.offsetMax = new Vector2(-22, -14);
            Img(Rect("Hex", head, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(10, 12)), "hex", Cyan);
            var title = Txt("Title", head, 18, TextMain, TextAnchor.MiddleLeft, true);
            title.text = "設定";
            Place(title.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(20, 0), new Vector2(200, 30));
            var close = Rect("Close", head, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(40, 40));
            var cb = GlassCircle(close, WithAlpha(Cyan, 0.35f));
            Icon(close, "close", 16, Hex(0xE6F8FF));
            close.gameObject.AddComponent<Button>().targetGraphic = cb;
            close.GetComponent<Button>().onClick.AddListener(() => OpenSheet(false));

            // タブ（声と会話・背景・そのほか）。1 つのタブの中身は、ほとんどの画面ですべらせずに見える量にする
            var tabs = Rect("Tabs", _sheet, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, Vector2.zero);
            tabs.anchorMin = new Vector2(0, 1);
            tabs.anchorMax = new Vector2(1, 1);
            tabs.offsetMin = new Vector2(22, -126);
            tabs.offsetMax = new Vector2(-22, -80);
            Pill(tabs, new Color(0.047f, 0.157f, 0.235f, 0.45f));
            Edge(tabs, WithAlpha(Cyan, 0.3f));
            var hl = tabs.gameObject.AddComponent<HorizontalLayoutGroup>();
            hl.padding = new RectOffset(4, 4, 4, 4);
            hl.spacing = 4;
            hl.childControlWidth = hl.childControlHeight = true;
            hl.childForceExpandWidth = hl.childForceExpandHeight = true;

            // 中身（入りきらなければ縦にすべらせる）。何もない所でもすべらせられるよう、見えない板で指を受ける
            var view = Rect("View", _sheet, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            view.anchorMin = Vector2.zero;
            view.anchorMax = Vector2.one;
            view.offsetMin = new Vector2(0, 40);
            view.offsetMax = new Vector2(0, -138);
            Img(view, null, Color.clear, raycast: true);
            view.gameObject.AddComponent<RectMask2D>();
            _sheetScroll = view.gameObject.AddComponent<ScrollRect>();
            _sheetScroll.horizontal = false;
            _sheetScroll.movementType = ScrollRect.MovementType.Elastic;   // 端で少し伸びて、すべらせられることが分かる
            _sheetScroll.elasticity = 0.12f;
            _sheetScroll.inertia = true;
            _sheetScroll.decelerationRate = 0.12f;
            _sheetScroll.scrollSensitivity = 40;   // PC のマウスのホイール
            _sheetScroll.viewport = view;

            var pages = new (string label, Action<RectTransform> build)[]
            {
                ("声と会話", c => { BuildVolumeSection(c); BuildTalkSection(c); BuildPresenceSection(c); }),
                ("背景", BuildBackgroundSection),
                ("そのほか", c => { BuildDevicesSection(c); BuildDevSection(c); }),
            };
            for (int i = 0; i < pages.Length; i++)
            {
                var content = Rect("Page_" + pages[i].label, view, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
                content.anchorMin = new Vector2(0, 1);
                content.anchorMax = new Vector2(1, 1);
                var vl = content.gameObject.AddComponent<VerticalLayoutGroup>();
                vl.padding = new RectOffset(22, 22, 8, 64);   // 下はホームのバーの分も空ける
                vl.spacing = 24;
                vl.childControlWidth = vl.childControlHeight = true;
                vl.childForceExpandWidth = true;
                vl.childForceExpandHeight = false;
                content.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
                pages[i].build(content);
                _pages.Add(content);

                var tab = new GameObject(pages[i].label, typeof(RectTransform));
                tab.transform.SetParent(tabs, false);
                var r = (RectTransform)tab.transform;
                var fill = Pill(r, WithAlpha(CyanDeep, 0.22f), raycast: true);
                var tabEdge = Edge(r, Cyan);
                var label = Txt("Label", r, 13, TextMain, TextAnchor.MiddleCenter);
                Stretch(label.rectTransform);
                label.text = pages[i].label;
                var b = tab.AddComponent<Button>();
                b.targetGraphic = fill;
                b.transition = Selectable.Transition.None;
                var index = i;
                b.onClick.AddListener(() => ShowPage(index));
                _tabs.Add((fill, tabEdge, label));
            }
            ShowPage(0);

            _sheetRoot.SetActive(false);
        }

        ScrollRect _sheetScroll;
        readonly List<RectTransform> _pages = new List<RectTransform>();
        readonly List<(Image fill, Image edge, Text label)> _tabs = new List<(Image, Image, Text)>();

        void ShowPage(int index)
        {
            for (int i = 0; i < _pages.Count; i++)
            {
                var sel = i == index;
                _pages[i].gameObject.SetActive(sel);
                var (fill, edge, label) = _tabs[i];
                fill.color = sel ? WithAlpha(CyanDeep, 0.22f) : Color.clear;
                edge.enabled = sel;
                label.fontStyle = sel ? FontStyle.Bold : FontStyle.Normal;
                label.color = sel ? TextMain : TextSub;
            }
            _sheetScroll.StopMovement();
            _sheetScroll.content = _pages[index];
            _pages[index].anchoredPosition = Vector2.zero;   // 先頭から見せる
        }

        void BuildVolumeSection(RectTransform content)
        {
            var sec = Section(content);
            var head = Row(sec, 28);
            var label = SectionLabel(head, "シエルの声の大きさ");
            label.alignment = TextAnchor.LowerLeft;
            _sheetValue = Txt("Value", head, 22, TextMain, TextAnchor.LowerRight, true);
            Stretch(_sheetValue.rectTransform);

            var row = Row(sec, 44);
            var low = Icon(row, "speaker_low", 18, TextNote);
            Place(low.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(18, 18));
            var high = Icon(row, "speaker", 18, Hex(0xE6F8FF));
            Place(high.rectTransform, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(18, 18));
            var sliderRect = Rect("Slider", row, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            sliderRect.anchorMin = Vector2.zero;
            sliderRect.anchorMax = Vector2.one;
            sliderRect.offsetMin = new Vector2(32, 0);
            sliderRect.offsetMax = new Vector2(-32, 0);
            _sheetSlider = BuildSlider(sliderRect, vertical: false);
            _sheetSlider.onValueChanged.AddListener(v => _conversation.SetVoiceVolume(v));

            Note(sec, "スマホ全体の音量とは別に、シエルの声だけを調整します");
        }

        void BuildBackgroundSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "背景");
            var options = CielBackground.Options;
            for (int r = 0; r < (options.Length + 1) / 2; r++)
            {
                var line = new GameObject("Line", typeof(RectTransform), typeof(HorizontalLayoutGroup), typeof(LayoutElement));
                line.transform.SetParent(sec, false);
                line.GetComponent<LayoutElement>().preferredHeight = 118;
                var hl = line.GetComponent<HorizontalLayoutGroup>();
                hl.spacing = 12;
                hl.childControlWidth = hl.childControlHeight = true;
                hl.childForceExpandWidth = hl.childForceExpandHeight = true;
                for (int c = 0; c < 2; c++)
                {
                    var i = r * 2 + c;
                    if (i < options.Length) BackgroundCell(line.transform, options[i]);
                    else new GameObject("Empty", typeof(RectTransform)).transform.SetParent(line.transform, false);
                }
            }
        }

        void BackgroundCell(Transform parent, CielBackground.Option option)
        {
            var cell = new GameObject(option.Key, typeof(RectTransform));
            cell.transform.SetParent(parent, false);
            var cr = (RectTransform)cell.transform;
            var hit = Img(cr, null, Color.clear, raycast: true);
            var button = cell.AddComponent<Button>();
            button.targetGraphic = hit;
            button.transition = Selectable.Transition.None;
            button.onClick.AddListener(() => _background.Set(option.Key));
            cell.AddComponent<PressScale>();

            var thumb = Rect("Thumb", cr, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            thumb.anchorMin = new Vector2(0, 1);
            thumb.anchorMax = new Vector2(1, 1);
            thumb.offsetMin = new Vector2(0, -92);
            thumb.offsetMax = Vector2.zero;
            Rounded(thumb, Color.white, 14);
            thumb.gameObject.AddComponent<Mask>().showMaskGraphic = false;
            var pic = Rect("Picture", thumb, Center, Center, Vector2.zero, Vector2.zero);
            var picImage = Img(pic, null, Color.white);
            picImage.sprite = option.Load();
            var fit = pic.gameObject.AddComponent<AspectRatioFitter>();
            fit.aspectMode = AspectRatioFitter.AspectMode.EnvelopeParent;
            if (picImage.sprite != null) fit.aspectRatio = picImage.sprite.rect.width / picImage.sprite.rect.height;
            var edgeRect = Rect("Edge", cr, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            edgeRect.anchorMin = new Vector2(0, 1);
            edgeRect.anchorMax = new Vector2(1, 1);
            edgeRect.offsetMin = new Vector2(0, -92);
            edgeRect.offsetMax = Vector2.zero;
            var edge = Img(edgeRect, "circle_outline", WithAlpha(Cyan, 0.25f));
            SetRadius(edge, 14);
            var check = Rect("Check", edgeRect, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-6, -6), new Vector2(22, 22));
            Img(check, "circle", CyanDeep);
            Icon(check, "check", 12, Ink);
            var label = Txt("Label", cr, 12, TextSub, TextAnchor.LowerLeft);
            Place(label.rectTransform, new Vector2(0, 0), new Vector2(0, 0), new Vector2(2, 0), new Vector2(160, 20));
            label.text = option.Label;
            _bgCells.Add((option.Key, edge, check.gameObject, label));
        }

        static readonly string[] TalkLabels = { "ひかえめ", "ふつう", "おしゃべり" };
        static readonly string[] TalkNotes =
        {
            "名前を呼ばれたときや、はっきり頼まれたときだけ答えます。",
            "話しかけられたら、毎回答えます。",
            "話しかけられたら答え、静かなときは自分からも話しかけます。返事がないときは、だんだん間をあけます。",
        };
        static readonly string[] PresenceLabels = { "自動", "ひとり", "身近な人", "人前" };
        static readonly string[] PresenceNotes =
        {
            "",
            "覚えていることを、シエルから話題にします。",
            "覚えていることは心に留めておき、話の流れで自然に生かします。",
            "覚えていることは話題にしません。本人に聞かれたら答えます。",
        };

        // おしゃべり度
        void BuildTalkSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "おしゃべり度");
            Segmented(sec, TalkLabels, i => _conversation.SelectTalk((CielConversation.Talk)i), _talkSegs);
            _talkNote = Txt("Note", sec, 12, TextSub, TextAnchor.UpperLeft);
        }

        // その場にいる人（覚えていることの出し方）
        void BuildPresenceSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "その場にいる人");
            Segmented(sec, PresenceLabels, i => _conversation.SelectPresence((CielConversation.Presence)i), _presenceSegs);
            _presenceNow = Txt("Now", sec, 12, TextMain, TextAnchor.UpperLeft, true);
            _presenceNote = Txt("Note", sec, 12, TextSub, TextAnchor.UpperLeft);
        }

        // PC だけ：マイクとスピーカーの選択
        void BuildDevicesSection(RectTransform content)
        {
            var sec = Section(content);
            _devicesSection = sec.gameObject;
            SectionLabel(Row(sec, 20), "マイクとスピーカー");
            _devices = NewDropdown(Row(sec, 44), "MicDevice");
            _devices.onValueChanged.AddListener(i => _conversation.SelectMic(i <= 0 ? null : _deviceGuids[i]));
            _speakers = NewDropdown(Row(sec, 44), "SpeakerDevice");
            _speakers.onValueChanged.AddListener(i => _conversation.SelectSpeaker(i <= 0 ? null : _speakerGuids[i]));
        }

        void BuildDevSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "開発");
            (_devServerSwitch, _devServerKnob) = SwitchRow(sec, "開発用のサーバーにつなぐ",
                () => _conversation.SetDevServer(!_conversation.DevServer));
            Note(sec, "試験・分析用のシエルにつなぎます。会話は調べるために記録され、7 日で消えます。切り替えると、つなぎ直します");
            (_exprSwitch, _exprKnob) = SwitchRow(sec, "表情の確認ボタンを出す", () =>
            {
                PlayerPrefs.SetInt(ExpressionPrefKey, ExpressionButtonsOn ? 0 : 1);
                Refresh();
            });
        }

        // 文字と、右端のスイッチの行。押すと click を呼ぶ（表示は ShowSwitch で合わせる）
        (Image sw, Image knob) SwitchRow(RectTransform sec, string label, Action click)
        {
            var row = Row(sec, 44);
            var hit = Img(row, null, Color.clear, raycast: true);
            var text = Txt("Text", row, 14, TextSub, TextAnchor.MiddleLeft);
            Stretch(text.rectTransform);
            text.text = label;
            var sw = Rect("Switch", row, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(48, 28));
            var bg = Pill(sw, Glass);
            Edge(sw, WithAlpha(Cyan, 0.45f));
            var knob = Img(Rect("Knob", sw, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(14, 0), new Vector2(20, 20)), "circle", TextSub);
            var b = row.gameObject.AddComponent<Button>();
            b.targetGraphic = hit;
            b.onClick.AddListener(() => click());
            return (bg, knob);
        }

        static void ShowSwitch(Image sw, Image knob, bool on)
        {
            sw.color = on ? WithAlpha(CyanDeep, 0.55f) : Glass;
            knob.color = on ? Color.white : TextSub;
            ((RectTransform)knob.transform).anchoredPosition = new Vector2(on ? 34 : 14, 0);
        }

        static bool ExpressionButtonsOn => PlayerPrefs.GetInt(ExpressionPrefKey, 0) == 1;

        void OpenSheet(bool open)
        {
            _sheetOpen = open;
            ShowVolumePop(false);
            if (open)
            {
                _sheetRoot.SetActive(true);
                Refresh();
            }
        }

        // 設定画面の表示を、いまの設定に合わせる（Refresh から呼ぶ）
        void RefreshSettings()
        {
            var c = _conversation;
            var talk = (int)c.CurrentTalk;
            var presence = (int)c.CurrentPresence;
            foreach (var (key, edge, check, label) in _bgCells)
            {
                var sel = _background != null && _background.Current == key;
                edge.color = sel ? Cyan : WithAlpha(Cyan, 0.25f);
                SetRadius(edge, 14, sel ? 1.5f : 1f);
                check.SetActive(sel);
                label.color = sel ? TextMain : TextSub;
            }
            ShowSelected(_talkSegs, (int)c.TalkChoice);
            _talkNote.text = c.CurrentTalk != c.TalkChoice
                ? TalkNotes[talk] + "（会議につないでいるあいだは、ひかえめにします）"
                : TalkNotes[talk];
            ShowSelected(_presenceSegs, (int)c.PresenceChoice);
            var why = c.PresenceReason == "meeting" ? "（会議につないでいる）" : c.PresenceReason == "voices" ? "（2人以上の声が聞こえた）" : "";
            _presenceNow.text = $"いまは：{PresenceLabels[presence]}{why}";
            _presenceNote.text = PresenceNotes[presence]
                + (c.PresenceChoice == CielConversation.Presence.Auto
                    ? "\n自動：会議につなぐと人前に、2人以上の声が聞こえると身近な人にします。" : "");
            _devicesSection.SetActive(c.CanSelectMic || c.CanSelectSpeaker);
            RefreshDevices(_devices, _deviceGuids, c.CanSelectMic, c.MicDevices, c.SelectedMic, "既定のマイク（OS の設定）", "マイク：");
            RefreshDevices(_speakers, _speakerGuids, c.CanSelectSpeaker, c.SpeakerDevices, c.SelectedSpeaker, "既定のスピーカー（OS の設定）", "声の出力：");
            var expr = ExpressionButtonsOn;
            if (_exprPanel != null) _exprPanel.SetActive(expr);
            ShowSwitch(_exprSwitch, _exprKnob, expr);
            ShowSwitch(_devServerSwitch, _devServerKnob, c.DevServer);
        }

        static void RefreshDevices(Dropdown dd, List<string> guids, bool can, List<(string name, string guid)> devices,
            string selected, string defaultName, string prefix)
        {
            dd.gameObject.SetActive(can);
            if (!can) return;
            if (guids.Count != devices.Count + 1)
            {
                guids.Clear();
                dd.ClearOptions();
                var names = new List<string> { prefix + defaultName };
                guids.Add(null);
                foreach (var (name, guid) in devices) { names.Add(prefix + name); guids.Add(guid); }
                dd.AddOptions(names);
            }
            dd.SetValueWithoutNotify(Mathf.Max(0, guids.IndexOf(selected)));
        }

        // 設定の出し入れ（下からすべり出る。Update から呼ぶ）
        void UpdateSheet()
        {
            var target = _sheetOpen ? 1f : 0f;
            if (!Mathf.Approximately(_sheetT, target))
            {
                _sheetT = Mathf.MoveTowards(_sheetT, target, Time.unscaledDeltaTime / 0.22f);
                var e = 1 - Mathf.Pow(1 - _sheetT, 3);
                _sheetGroup.alpha = e;
                _sheet.anchoredPosition = new Vector2(0, -(1 - e) * 220);
                if (_sheetT <= 0) _sheetRoot.SetActive(false);
            }
        }
    }
}
