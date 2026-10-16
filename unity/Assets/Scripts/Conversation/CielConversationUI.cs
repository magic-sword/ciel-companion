// 会話の画面（A案「シエルの視界」）。デザインは CIEL Companion UI案のキャンバス（A案・設定・その場で音量）。
// 下の中央に Ciel Prism の形のマイクボタン、左に議事録、右に声の出力（Android はタップでスピーカー・受話口、
// 長押しで声の大きさ。PC はタップで声の大きさ）。上に接続の状態、会話のモード、設定のボタン。
// 設定画面：シエルの声の大きさ、背景（CielBackground）、会話のしかた、PC ではマイクとスピーカー、開発用の表情の確認ボタン。
// 画面の部品は実行時にコードで作る（シーンに置くのは、このコンポーネントだけ）。
// 形とアイコンの画像は Assets/Resources/CielUI（scripts/ui/make_ui_sprites.py が作る。白一色で、色はここで付ける）。
// 寸法はモックアップ（390×844）の値。上下の位置は、端末の切り欠きを除いた範囲（Screen.safeArea）から測る。
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    public sealed class CielConversationUI : MonoBehaviour
    {
        [SerializeField] CielConversation _conversation;
        [SerializeField] CielBackground _background;

        // 色：白磁・シアン・チャコールと、議事録の琥珀（企画設計の「シエル主観視界」の色の決まり）
        static readonly Color Cyan = Hex(0x7FE9FF), CyanDeep = Hex(0x2CC8EE), Ink = Hex(0x04293D);
        static readonly Color TextMain = Hex(0xF4FBFF), TextSub = Hex(0xCDEFFA), TextNote = Hex(0x8FB3C3), SectionText = Hex(0x9FDDF0);
        static readonly Color Mint = Hex(0x5BF0C8), Amber = Hex(0xFFC46B), Alert = Hex(0xFF9A8A), Idle = Hex(0x8FA3B0);
        static readonly Color Glass = new Color(0.047f, 0.157f, 0.235f, 0.42f);
        static readonly Color AmberGlass = new Color(0.36f, 0.24f, 0.04f, 0.55f);
        static readonly Color SheetColor = new Color(0.04f, 0.10f, 0.16f, 0.95f);

        const string ExpressionPrefKey = "ciel.ui.expressionButtons";
        const float LongPress = 0.45f;

        Font _font;
        RectTransform _canvasRect, _safe;

        // 上
        Image _linkDot;
        Text _linkText, _modeText;
        // 声の様子と状態
        readonly List<RectTransform> _bars = new List<RectTransform>();
        readonly List<Image> _barImages = new List<Image>();
        Text _status, _caption;
        // マイク
        Button _micButton;
        Image _micHex, _micGlow, _micIcon, _ringBreath, _ringDots;
        // 議事録・声の出力
        Button _minutesButton;
        Image _minutesBg, _minutesEdge, _minutesIcon, _speakerIcon;
        Text _minutesLabel, _speakerLabel;
        // その場の声の大きさ
        GameObject _volumePop;
        Slider _popSlider;
        Text _popValue;
        // 設定
        GameObject _sheetRoot;
        RectTransform _sheet;
        CanvasGroup _sheetGroup;
        float _sheetT;
        bool _sheetOpen;
        Slider _sheetSlider;
        Text _sheetValue;
        readonly List<(string key, Image edge, GameObject check, Text label)> _bgCells = new List<(string, Image, GameObject, Text)>();
        readonly List<(CielConversation.ModeSetting mode, Image fill, Image edge, Text label)> _modeSegs = new List<(CielConversation.ModeSetting, Image, Image, Text)>();
        GameObject _devicesSection;
        Dropdown _devices, _speakers;
        readonly List<string> _deviceGuids = new List<string>();
        readonly List<string> _speakerGuids = new List<string>();
        Image _exprSwitch, _exprKnob;
        // 開発用の表情の確認ボタン
        GameObject _exprPanel;

        void Awake()
        {
            if (_conversation == null) _conversation = FindAnyObjectByType<CielConversation>();
            if (_background == null) _background = FindAnyObjectByType<CielBackground>();
            if (_background == null) _background = gameObject.AddComponent<CielBackground>();
            _font = Font.CreateDynamicFontFromOSFont(
                new[] { "Yu Gothic UI", "Meiryo UI", "Meiryo", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP" }, 32);
            Build();
        }

        void OnEnable()
        {
            if (_conversation != null) _conversation.Changed += Refresh;
            if (_background != null) _background.Changed += Refresh;
            Refresh();
        }

        void OnDisable()
        {
            if (_conversation != null) _conversation.Changed -= Refresh;
            if (_background != null) _background.Changed -= Refresh;
        }

        // ---- 組み立て ----

        void Build()
        {
            if (FindAnyObjectByType<EventSystem>() == null)
                new GameObject("EventSystem", typeof(EventSystem), typeof(InputSystemUIInputModule));

            var canvasGo = new GameObject("ConversationCanvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(390, 844);
            scaler.matchWidthOrHeight = 0.5f;
            _canvasRect = (RectTransform)canvasGo.transform;

            BuildScrims(_canvasRect);
            _safe = Rect("SafeArea", _canvasRect, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(_safe);
            _safe.gameObject.AddComponent<SafeArea>();

            BuildTop(_safe);
            BuildExpressionButtons(_safe);
            BuildVoiceStatus(_safe);
            BuildBottomRow(_safe);
            BuildVolumePop(_canvasRect);
            BuildSheet(_canvasRect);
        }

        // 画面の上と下を少し暗くして、文字を読みやすくする。左右の上の隅に、シエルの視界の細い弧
        void BuildScrims(RectTransform root)
        {
            var bottom = Rect("ScrimBottom", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), Vector2.zero, Vector2.zero);
            bottom.anchorMin = new Vector2(0, 0);
            bottom.anchorMax = new Vector2(1, 0.5f);
            bottom.offsetMin = bottom.offsetMax = Vector2.zero;
            Img(bottom, "fade", new Color(0.024f, 0.07f, 0.12f, 0.9f));   // シエルの白い体の上でも、文字とボタンが読めるように

            var top = Rect("ScrimTop", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), Vector2.zero, Vector2.zero);
            top.anchorMin = new Vector2(0, 0.78f);
            top.anchorMax = new Vector2(1, 1);
            top.offsetMin = top.offsetMax = Vector2.zero;
            top.localScale = new Vector3(1, -1, 1);   // 上ほど濃く（画像は下ほど濃い）
            Img(top, "fade", new Color(0.04f, 0.11f, 0.17f, 0.35f));

            var left = Rect("ArcLeft", root, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, new Vector2(128, 128));
            Img(left, "corner_arc", WithAlpha(Cyan, 0.55f));
            var right = Rect("ArcRight", root, new Vector2(1, 1), new Vector2(0, 1), Vector2.zero, new Vector2(128, 128));
            right.localScale = new Vector3(-1, 1, 1);
            Img(right, "corner_arc", WithAlpha(Cyan, 0.55f));
        }

        void BuildTop(RectTransform root)
        {
            var name = Txt("Name", root, 13, TextMain, TextAnchor.UpperLeft, true);
            name.text = "C I E L";
            Place(name.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(24, -12), new Vector2(120, 20));

            // 接続の状態。つながっていないときはタップでつなぎ直す
            var link = Rect("Link", root, new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -30), new Vector2(230, 24));
            var linkHit = Img(link, null, Color.clear, raycast: true);
            var linkButton = link.gameObject.AddComponent<Button>();
            linkButton.targetGraphic = linkHit;
            linkButton.onClick.AddListener(() =>
            {
                var s = _conversation.Status;
                if (s == CielConversation.State.Failed || s == CielConversation.State.Disconnected) _conversation.StartConversation();
            });
            var dot = Rect("Dot", link, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(6, 0), new Vector2(6, 6));
            _linkDot = Img(dot, "circle", Mint);
            var dotGlow = Rect("Glow", dot, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(20, 20));
            Img(dotGlow, "glow", WithAlpha(Mint, 0.6f));
            _linkText = Txt("Text", link, 11, TextSub, TextAnchor.MiddleLeft);
            Place(_linkText.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(18, 0), new Vector2(210, 20));
            _linkText.horizontalOverflow = HorizontalWrapMode.Overflow;

            // 設定のボタン
            var settings = Rect("SettingsButton", root, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -6), new Vector2(36, 36));
            var sb = GlassCircle(settings, WithAlpha(Cyan, 0.35f));
            Icon(settings, "settings", 16, Hex(0xE6F8FF));
            settings.gameObject.AddComponent<Button>().targetGraphic = sb;
            settings.GetComponent<Button>().onClick.AddListener(() => OpenSheet(true));

            // 会話のモード（タップで 自動 → 2 人 → みんなで → 自動）
            var mode = Rect("ModeButton", root, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-64, -6), new Vector2(118, 36));
            var mb = Pill(mode, Glass, raycast: true);
            Edge(mode, WithAlpha(Cyan, 0.55f));
            var icon = Icon(mode, "people", 14, Cyan);
            Place(icon.rectTransform, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(21, 0), new Vector2(14, 14));
            _modeText = Txt("Text", mode, 12, TextMain, TextAnchor.MiddleLeft);
            Place(_modeText.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(34, 0), new Vector2(80, 20));
            _modeText.horizontalOverflow = HorizontalWrapMode.Overflow;
            var modeButton = mode.gameObject.AddComponent<Button>();
            modeButton.targetGraphic = mb;
            modeButton.onClick.AddListener(() =>
                _conversation.SelectMode((CielConversation.ModeSetting)(((int)_conversation.ModeChoice + 1) % 3)));
        }

        void BuildVoiceStatus(RectTransform root)
        {
            // シエルの声の様子（話しているときは声に合わせ、聞いているときは静かに揺れる）
            var wave = Rect("Wave", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 193), new Vector2(120, 18));
            for (int i = 0; i < 15; i++)
            {
                var bar = Rect("Bar", wave, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(3.5f + i * 8, 0), new Vector2(3, 4));
                _bars.Add(bar);
                _barImages.Add(Pill(bar, Cyan));
            }

            _status = Txt("Status", root, 17, TextMain, TextAnchor.MiddleCenter);
            Place(_status.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 164), new Vector2(360, 28));
            var shadow = _status.gameObject.AddComponent<Shadow>();
            shadow.effectColor = new Color(0, 0.08f, 0.16f, 0.8f);
            shadow.effectDistance = new Vector2(0, -1.5f);

            _caption = Txt("Caption", root, 9, WithAlpha(TextSub, 0.55f), TextAnchor.MiddleCenter);
            Place(_caption.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 6), new Vector2(200, 14));
        }

        void BuildBottomRow(RectTransform root)
        {
            // マイク（Ciel Prism の六角）。入れているあいだは、まわりの輪が呼吸するように光る
            var mic = Rect("MicButton", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 74), new Vector2(112, 112));
            var hit = Img(mic, null, Color.clear, raycast: true);
            _micGlow = Img(Rect("Glow", mic, Center, Center, Vector2.zero, new Vector2(150, 166)), "hex_glow", WithAlpha(CyanDeep, 0.8f));
            _ringBreath = Img(Rect("Ring", mic, Center, Center, Vector2.zero, new Vector2(112, 112)), "ring", Cyan);
            _ringDots = Img(Rect("Dots", mic, Center, Center, Vector2.zero, new Vector2(92, 92)), "ring_dotted", WithAlpha(Cyan, 0.7f));
            _micHex = Img(Rect("Hex", mic, Center, Center, Vector2.zero, new Vector2(76, 84)), "hex_prism", Color.white);
            _micIcon = Icon(mic, "mic", 28, Ink);
            _micButton = mic.gameObject.AddComponent<Button>();
            _micButton.targetGraphic = hit;
            _micButton.transition = Selectable.Transition.None;
            _micButton.onClick.AddListener(() => _conversation.SetMicEnabled(!_conversation.MicEnabled));
            mic.gameObject.AddComponent<PressScale>();

            // 議事録
            var minutes = Rect("MinutesButton", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(-132, 74), new Vector2(64, 92));
            var mHit = Img(minutes, null, Color.clear, raycast: true);
            var mCircle = Rect("Circle", minutes, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, new Vector2(52, 52));
            _minutesBg = Img(mCircle, "circle", Glass);
            _minutesEdge = Edge(mCircle, WithAlpha(Cyan, 0.45f));
            _minutesIcon = Icon(mCircle, "minutes", 20, Hex(0xE6F8FF));
            _minutesLabel = Txt("Label", minutes, 11, TextSub, TextAnchor.MiddleCenter);
            Place(_minutesLabel.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 16), new Vector2(90, 16));
            _minutesButton = minutes.gameObject.AddComponent<Button>();
            _minutesButton.targetGraphic = mHit;
            _minutesButton.transition = Selectable.Transition.None;
            _minutesButton.onClick.AddListener(() => _conversation.SetMinutes(!_conversation.MinutesOn));
            minutes.gameObject.AddComponent<PressScale>();

            // 声の出力（Android：タップでスピーカー・受話口、長押しで声の大きさ。PC：タップで声の大きさ）
            var speaker = Rect("SpeakerButton", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(132, 74), new Vector2(64, 92));
            Img(speaker, null, Color.clear, raycast: true);
            var sCircle = Rect("Circle", speaker, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, new Vector2(52, 52));
            Img(sCircle, "circle", Glass);
            Edge(sCircle, WithAlpha(Cyan, 0.45f));
            _speakerIcon = Icon(sCircle, "speaker", 20, Hex(0xE6F8FF));
            _speakerLabel = Txt("Label", speaker, 11, TextSub, TextAnchor.MiddleCenter);
            Place(_speakerLabel.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 16), new Vector2(90, 16));
            var press = speaker.gameObject.AddComponent<PressScale>();
            press.Click = () =>
            {
                if (_conversation.CanUseSpeakerphone) _conversation.SetSpeakerphone(!_conversation.SpeakerphoneOn);
                else ShowVolumePop(!_volumePop.activeSelf);
            };
            press.Hold = () => ShowVolumePop(true);
        }

        // その場で声の大きさを変える縦のつまみ（声の出力のボタンの上）
        void BuildVolumePop(RectTransform root)
        {
            _volumePop = new GameObject("VolumePop", typeof(RectTransform));
            var pop = (RectTransform)_volumePop.transform;
            pop.SetParent(root, false);
            Stretch(pop);
            var blocker = Img(pop, null, Color.clear, raycast: true);   // 外を押したら閉じる
            blocker.gameObject.AddComponent<Button>().onClick.AddListener(() => ShowVolumePop(false));

            var area = Rect("Safe", pop, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(area);
            area.gameObject.AddComponent<SafeArea>();
            var panel = Rect("Panel", area, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(132, 136), new Vector2(64, 236));
            Pill(panel, new Color(0.04f, 0.13f, 0.20f, 0.88f), raycast: true);
            Edge(panel, WithAlpha(Cyan, 0.55f));
            _popValue = Txt("Value", panel, 18, TextMain, TextAnchor.MiddleCenter, true);
            Place(_popValue.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -28), new Vector2(60, 24));
            var label = Txt("Label", panel, 10, TextSub, TextAnchor.MiddleCenter);
            label.text = "声";
            Place(label.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 22), new Vector2(60, 16));
            var sliderRect = Rect("Slider", panel, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 40), new Vector2(40, 150));
            _popSlider = BuildSlider(sliderRect, vertical: true);
            _popSlider.onValueChanged.AddListener(v => _conversation.SetVoiceVolume(v));
            _volumePop.SetActive(false);
        }

        void ShowVolumePop(bool on) => _volumePop.SetActive(on);

        // ---- 設定 ----

        void BuildSheet(RectTransform root)
        {
            _sheetRoot = new GameObject("Settings", typeof(RectTransform), typeof(CanvasGroup));
            var sr = (RectTransform)_sheetRoot.transform;
            sr.SetParent(root, false);
            Stretch(sr);
            _sheetGroup = _sheetRoot.GetComponent<CanvasGroup>();
            var dim = Img(sr, null, new Color(0.01f, 0.04f, 0.07f, 0.55f), raycast: true);
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

            // 中身（縦に並べ、入りきらなければ縦にすべらせる）
            var view = Rect("View", _sheet, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            view.anchorMin = Vector2.zero;
            view.anchorMax = Vector2.one;
            view.offsetMin = new Vector2(0, 40);
            view.offsetMax = new Vector2(0, -76);
            view.gameObject.AddComponent<RectMask2D>();
            var scroll = view.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            var content = Rect("Content", view, new Vector2(0.5f, 1), new Vector2(0.5f, 1), Vector2.zero, Vector2.zero);
            content.anchorMin = new Vector2(0, 1);
            content.anchorMax = new Vector2(1, 1);
            content.pivot = new Vector2(0.5f, 1);
            var vl = content.gameObject.AddComponent<VerticalLayoutGroup>();
            vl.padding = new RectOffset(22, 22, 4, 40);
            vl.spacing = 24;
            vl.childControlWidth = vl.childControlHeight = true;
            vl.childForceExpandWidth = true;
            vl.childForceExpandHeight = false;
            content.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            scroll.viewport = view;
            scroll.content = content;

            BuildVolumeSection(content);
            BuildBackgroundSection(content);
            BuildModeSection(content);
            BuildDevicesSection(content);
            BuildDevSection(content);

            _sheetRoot.SetActive(false);
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

        void BuildModeSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "会話のしかた");
            var bar = Row(sec, 46);
            Pill(bar, new Color(0.047f, 0.157f, 0.235f, 0.45f));
            Edge(bar, WithAlpha(Cyan, 0.3f));
            var hl = bar.gameObject.AddComponent<HorizontalLayoutGroup>();
            hl.padding = new RectOffset(4, 4, 4, 4);
            hl.spacing = 4;
            hl.childControlWidth = hl.childControlHeight = true;
            hl.childForceExpandWidth = hl.childForceExpandHeight = true;
            var items = new[] { (CielConversation.ModeSetting.Auto, "自動"), (CielConversation.ModeSetting.Solo, "2人"), (CielConversation.ModeSetting.Group, "みんなで") };
            foreach (var (mode, text) in items)
            {
                var seg = new GameObject(text, typeof(RectTransform));
                seg.transform.SetParent(bar, false);
                var r = (RectTransform)seg.transform;
                var fill = Pill(r, WithAlpha(CyanDeep, 0.22f), raycast: true);
                var edge = Edge(r, Cyan);
                var label = Txt("Label", r, 13, TextMain, TextAnchor.MiddleCenter);
                Stretch(label.rectTransform);
                label.text = text;
                var b = seg.AddComponent<Button>();
                b.targetGraphic = fill;
                b.transition = Selectable.Transition.None;
                var m = mode;
                b.onClick.AddListener(() => _conversation.SelectMode(m));
                _modeSegs.Add((mode, fill, edge, label));
            }
            Note(sec, "みんなで：名前を呼ばれたときだけ答えます\n自動：会議へつないでいるときは、みんなで");
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
            var row = Row(sec, 44);
            var hit = Img(row, null, Color.clear, raycast: true);
            var text = Txt("Text", row, 14, TextSub, TextAnchor.MiddleLeft);
            Stretch(text.rectTransform);
            text.text = "表情の確認ボタンを出す";
            var sw = Rect("Switch", row, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(48, 28));
            _exprSwitch = Pill(sw, Glass);
            Edge(sw, WithAlpha(Cyan, 0.45f));
            _exprKnob = Img(Rect("Knob", sw, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(14, 0), new Vector2(20, 20)), "circle", TextSub);
            var b = row.gameObject.AddComponent<Button>();
            b.targetGraphic = hit;
            b.onClick.AddListener(() =>
            {
                PlayerPrefs.SetInt(ExpressionPrefKey, ExpressionButtonsOn ? 0 : 1);
                Refresh();
            });
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

        // 表情の確認用のボタン（開発用。設定で出す）
        void BuildExpressionButtons(RectTransform root)
        {
            var expression = FindAnyObjectByType<CielExpression>();
            if (expression == null) return;
            _exprPanel = new GameObject("ExpressionButtons", typeof(RectTransform));
            var panel = (RectTransform)_exprPanel.transform;
            panel.SetParent(root, false);
            Stretch(panel);
            var names = CielExpression.Names;
            for (int i = 0; i < names.Length; i++)
            {
                var n = names[i];
                var r = Rect("Expr_" + n, panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-20, -56 - i * 34), new Vector2(92, 28));
                var bg = Pill(r, Glass, raycast: true);
                Edge(r, WithAlpha(Cyan, 0.3f));
                var b = r.gameObject.AddComponent<Button>();
                b.targetGraphic = bg;
                b.onClick.AddListener(() => expression.Set(n, 4f));
                var t = Txt("Label", r, 12, TextMain, TextAnchor.MiddleCenter);
                Stretch(t.rectTransform);
                t.text = CielExpression.JapaneseNames[n];
            }
        }

        // ---- 表示の更新 ----

        void Refresh()
        {
            if (_micHex == null || _conversation == null) return;
            var c = _conversation;
            var connected = c.Status == CielConversation.State.Connected;

            (_linkDot.color, _linkText.text) = c.Status switch
            {
                CielConversation.State.Connecting => (Amber, "つないでいます…"),
                CielConversation.State.Failed => (Alert, "つながりませんでした（タップでやり直す）"),
                CielConversation.State.Disconnected => (Idle, "つながっていません（タップでつなぐ）"),
                _ => (Mint, "つながっています"),
            };
            _linkDot.transform.GetChild(0).GetComponent<Image>().color = WithAlpha(_linkDot.color, 0.6f);

            var current = c.CurrentMode == CielConversation.Mode.Group ? "みんなで" : "2人";
            _modeText.text = c.ModeChoice == CielConversation.ModeSetting.Auto ? $"自動 · {current}" : current;

            _status.text = c.Status switch
            {
                CielConversation.State.Connecting => "シエルに接続しています…",
                CielConversation.State.Failed => "接続できませんでした",
                CielConversation.State.Disconnected => "接続していません",
                _ => c.MicEnabled ? "話しかけてください" : "マイクを入れると話せます",
            };
            _caption.text = connected && c.MicEnabled ? "L I S T E N I N G" : "";

            // マイク：入れている（光る六角）・切っている（透けた六角）・使えない（薄い）
            var usable = connected && !c.MicBusy;
            _micButton.interactable = usable;
            var on = c.MicEnabled && connected;
            _micHex.sprite = LoadSprite(on ? "hex_prism" : "hex");
            // 切っているときは濃い色のガラス（シエルの白い体の上でも形が見える）
            _micHex.color = on ? Color.white : usable ? new Color(0.05f, 0.18f, 0.27f, 0.85f) : new Color(0.05f, 0.14f, 0.2f, 0.6f);
            _micIcon.color = on ? Ink : WithAlpha(Hex(0xE6F8FF), usable ? 1f : 0.4f);
            _micGlow.gameObject.SetActive(on);
            _ringDots.gameObject.SetActive(on);
            _ringBreath.color = WithAlpha(Cyan, on ? 0.6f : usable ? 0.35f : 0.12f);

            // 議事録：とっているあいだは琥珀
            _minutesButton.interactable = connected;
            var rec = c.MinutesOn;
            _minutesBg.color = rec ? AmberGlass : Glass;
            _minutesEdge.color = rec ? WithAlpha(Amber, 0.8f) : WithAlpha(Cyan, connected ? 0.45f : 0.18f);
            _minutesIcon.color = rec ? Amber : WithAlpha(Hex(0xE6F8FF), connected ? 1f : 0.4f);
            _minutesLabel.text = rec ? "記録中" : "議事録";
            _minutesLabel.color = rec ? Amber : TextSub;

            // 声の出力
            var phone = c.CanUseSpeakerphone;
            _speakerIcon.sprite = LoadSprite("Icons/" + (phone && !c.SpeakerphoneOn ? "earpiece" : "speaker"));
            _speakerLabel.text = !phone ? "声の大きさ" : c.SpeakerphoneOn ? "スピーカー" : "受話口";

            // 声の大きさ
            var volume = Mathf.RoundToInt(c.VoiceVolume * 100);
            _popValue.text = _sheetValue.text = volume.ToString();
            _popSlider.SetValueWithoutNotify(c.VoiceVolume);
            _sheetSlider.SetValueWithoutNotify(c.VoiceVolume);

            // 設定：背景・会話のしかた・機器・開発
            foreach (var (key, edge, check, label) in _bgCells)
            {
                var sel = _background != null && _background.Current == key;
                edge.color = sel ? Cyan : WithAlpha(Cyan, 0.25f);
                SetRadius(edge, 14, sel ? 1.5f : 1f);
                check.SetActive(sel);
                label.color = sel ? TextMain : TextSub;
            }
            foreach (var (mode, fill, edge, label) in _modeSegs)
            {
                var sel = c.ModeChoice == mode;
                fill.color = sel ? WithAlpha(CyanDeep, 0.22f) : Color.clear;
                edge.enabled = sel;
                label.fontStyle = sel ? FontStyle.Bold : FontStyle.Normal;
                label.color = sel ? TextMain : TextSub;
            }
            _devicesSection.SetActive(c.CanSelectMic || c.CanSelectSpeaker);
            RefreshDevices(_devices, _deviceGuids, c.CanSelectMic, c.MicDevices, c.SelectedMic, "既定のマイク（OS の設定）", "マイク：");
            RefreshDevices(_speakers, _speakerGuids, c.CanSelectSpeaker, c.SpeakerDevices, c.SelectedSpeaker, "既定のスピーカー（OS の設定）", "声の出力：");
            var expr = ExpressionButtonsOn;
            if (_exprPanel != null) _exprPanel.SetActive(expr);
            _exprSwitch.color = expr ? WithAlpha(CyanDeep, 0.55f) : Glass;
            _exprKnob.color = expr ? Color.white : TextSub;
            ((RectTransform)_exprKnob.transform).anchoredPosition = new Vector2(expr ? 34 : 14, 0);
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

        // ---- 動き ----

        bool _firstRefresh;

        void Update()
        {
            if (_conversation == null) return;
            // CielConversation は保存した設定（モード・声の大きさ）を Start で読むので、全部の Start のあとに表示を合わせる
            if (!_firstRefresh) { _firstRefresh = true; Refresh(); }
            var t = Time.unscaledTime;
            var c = _conversation;
            var on = c.MicEnabled && c.Status == CielConversation.State.Connected;

            if (on)
            {
                var s = (Mathf.Sin(t * Mathf.PI * 2 / 2.4f) + 1) / 2;   // 2.4 秒で 1 回の呼吸
                _ringBreath.color = WithAlpha(Cyan, 0.35f + 0.55f * s);
                _ringBreath.transform.localScale = Vector3.one * (1 + 0.06f * s);
                _ringDots.transform.localEulerAngles = new Vector3(0, 0, -t * 360f / 14f);
                _micGlow.color = WithAlpha(CyanDeep, 0.55f + 0.3f * s);
            }
            else _ringBreath.transform.localScale = Vector3.one;

            if (c.MinutesOn)
                _minutesEdge.color = WithAlpha(Amber, 0.45f + 0.45f * (Mathf.Sin(t * Mathf.PI * 2 / 1.6f) + 1) / 2);

            // 声の様子
            var level = Mathf.Clamp01(c.VoiceLevel * 8f);
            for (int i = 0; i < _bars.Count; i++)
            {
                var env = Mathf.Sin(Mathf.PI * (i + 0.5f) / _bars.Count);
                float h;
                if (level > 0.02f) h = 3 + 15 * level * env * (0.45f + 0.55f * Mathf.Abs(Mathf.Sin(t * 9f + i * 1.3f)));
                else if (on) h = 3 + 6 * env * (0.5f + 0.5f * Mathf.Sin(t * 3f + i * 0.7f));
                else h = 3;
                _bars[i].sizeDelta = new Vector2(3, h);
                _barImages[i].color = WithAlpha(Cyan, level > 0.02f || on ? 1f : 0.35f);
            }

            // 設定の出し入れ（下からすべり出る）
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

        // ---- 部品 ----

        static readonly Vector2 Center = new Vector2(0.5f, 0.5f);
        static readonly Dictionary<string, Sprite> Sprites = new Dictionary<string, Sprite>();

        static Sprite LoadSprite(string name)
        {
            if (name == null) return null;
            if (!Sprites.TryGetValue(name, out var s))
            {
                s = Resources.Load<Sprite>("CielUI/" + name);
                if (s == null) Debug.LogWarning($"[CielConversationUI] 画像 CielUI/{name} がない");
                Sprites[name] = s;
            }
            return s;
        }

        static Color Hex(int rgb) => new Color(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f);
        static Color WithAlpha(Color c, float a) => new Color(c.r, c.g, c.b, a);

        static RectTransform Rect(string name, Transform parent, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = (RectTransform)go.transform;
            Place(r, anchor, pivot, pos, size);
            return r;
        }

        static void Place(RectTransform r, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            r.anchorMin = r.anchorMax = anchor;
            r.pivot = pivot;
            r.anchoredPosition = pos;
            r.sizeDelta = size;
        }

        static void Stretch(RectTransform r)
        {
            r.anchorMin = Vector2.zero;
            r.anchorMax = Vector2.one;
            r.offsetMin = r.offsetMax = Vector2.zero;
        }

        /// 画像。child なら同じ大きさの子を作ってそこへ置く（1 つの部品に何枚も重ねるため）
        static Image Img(RectTransform r, string sprite, Color color, bool raycast = false, bool child = false)
        {
            if (child || r.GetComponent<Graphic>() != null)
            {
                var c = new GameObject(sprite ?? "Image", typeof(RectTransform), typeof(LayoutElement));
                c.GetComponent<LayoutElement>().ignoreLayout = true;   // 重ねる画像は、並べる対象にしない
                c.transform.SetParent(r, false);
                r = (RectTransform)c.transform;
                Stretch(r);
            }
            var img = r.gameObject.AddComponent<Image>();
            img.sprite = LoadSprite(sprite);
            img.color = color;
            img.raycastTarget = raycast;
            return img;
        }

        // 丸の画像を 9 分割で伸ばして、角の半径 radius の板にする
        static void SetRadius(Image img, float radius, float edge = 1f)
        {
            img.type = Image.Type.Sliced;
            img.fillCenter = img.sprite == null || img.sprite.name != "circle_outline";
            img.pixelsPerUnitMultiplier = 63f / Mathf.Max(radius, 1f) / edge;
        }

        static Image Rounded(RectTransform r, Color color, float radius, bool raycast = false)
        {
            var img = Img(r, "circle", color, raycast);
            SetRadius(img, radius);
            return img;
        }

        // カプセル（短い辺の半分を半径にする）
        static Image Pill(RectTransform r, Color color, bool raycast = false)
        {
            var img = Img(r, "circle", color, raycast);
            img.type = Image.Type.Sliced;
            img.gameObject.AddComponent<PillRadius>();
            return img;
        }

        // 細い光の縁（カプセルの形）
        static Image Edge(RectTransform r, Color color)
        {
            var img = Img(r, "circle_outline", color, child: true);
            img.type = Image.Type.Sliced;
            img.fillCenter = false;
            img.gameObject.AddComponent<PillRadius>();
            return img;
        }

        static Image GlassCircle(RectTransform r, Color edge)
        {
            var bg = Img(r, "circle", Glass, raycast: true);
            Edge(r, edge);
            return bg;
        }

        static Image Icon(RectTransform parent, string name, float size, Color color)
        {
            var r = Rect(name, parent, Center, Center, Vector2.zero, new Vector2(size, size));
            return Img(r, "Icons/" + name, color);
        }

        Text Txt(string name, Transform parent, int size, Color color, TextAnchor align, bool bold = false)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Text));
            go.transform.SetParent(parent, false);
            var t = go.GetComponent<Text>();
            t.font = _font;
            t.fontSize = size;
            t.fontStyle = bold ? FontStyle.Bold : FontStyle.Normal;
            t.alignment = align;
            t.color = color;
            t.raycastTarget = false;
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            return t;
        }

        // 設定の部品：縦に並ぶまとまり・決まった高さの行・見出し・注記
        static RectTransform Section(RectTransform content)
        {
            var go = new GameObject("Section", typeof(RectTransform), typeof(VerticalLayoutGroup));
            go.transform.SetParent(content, false);
            var vl = go.GetComponent<VerticalLayoutGroup>();
            vl.spacing = 12;
            vl.childControlWidth = vl.childControlHeight = true;
            vl.childForceExpandWidth = true;
            vl.childForceExpandHeight = false;
            return (RectTransform)go.transform;
        }

        static RectTransform Row(RectTransform section, float height)
        {
            var go = new GameObject("Row", typeof(RectTransform), typeof(LayoutElement));
            go.transform.SetParent(section, false);
            go.GetComponent<LayoutElement>().preferredHeight = height;
            return (RectTransform)go.transform;
        }

        Text SectionLabel(RectTransform row, string text)
        {
            var t = Txt("Label", row, 13, SectionText, TextAnchor.MiddleLeft, true);
            Stretch(t.rectTransform);
            t.text = text;
            return t;
        }

        // 文字の量に合わせた高さで並ぶ（Text が自分の高さを知らせる）
        void Note(RectTransform section, string text)
        {
            var t = Txt("Note", section, 11, TextNote, TextAnchor.UpperLeft);
            t.text = text;
        }

        // 細い光の線と六角のつまみ
        Slider BuildSlider(RectTransform r, bool vertical)
        {
            var hit = Img(r, null, Color.clear, raycast: true);
            var track = Rect("Track", r, Center, Center, Vector2.zero, Vector2.zero);
            Bar(track, vertical);
            Pill(track, WithAlpha(Cyan, 0.18f));
            var fillArea = Rect("FillArea", r, Center, Center, Vector2.zero, Vector2.zero);
            Bar(fillArea, vertical);
            var fill = Rect("Fill", fillArea, Center, Center, Vector2.zero, Vector2.zero);
            fill.sizeDelta = Vector2.zero;
            Pill(fill, CyanDeep);
            var handleArea = Rect("HandleArea", r, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(handleArea);
            if (vertical) { handleArea.offsetMin = new Vector2(0, 12); handleArea.offsetMax = new Vector2(0, -12); }
            else { handleArea.offsetMin = new Vector2(11, 0); handleArea.offsetMax = new Vector2(-11, 0); }
            // Slider は、つまみを動かす向きと直角の向きに伸ばすので、見た目の六角は真ん中に決まった大きさで置く
            var handle = Rect("Handle", handleArea, Center, Center, Vector2.zero, Vector2.zero);
            Img(Rect("Glow", handle, Center, Center, Vector2.zero, new Vector2(44, 48)), "hex_glow", WithAlpha(CyanDeep, 0.6f));
            Img(Rect("Hex", handle, Center, Center, Vector2.zero, new Vector2(22, 25)), "hex_prism", Color.white);

            var s = r.gameObject.AddComponent<Slider>();
            s.direction = vertical ? Slider.Direction.BottomToTop : Slider.Direction.LeftToRight;
            s.fillRect = fill;
            s.handleRect = handle;
            s.targetGraphic = hit;
            s.transition = Selectable.Transition.None;
            s.minValue = 0;
            s.maxValue = 1;
            handle.sizeDelta = vertical ? new Vector2(0, 25) : new Vector2(22, 0);
            return s;

            void Bar(RectTransform b, bool v)
            {
                if (v)
                {
                    b.anchorMin = new Vector2(0.5f, 0);
                    b.anchorMax = new Vector2(0.5f, 1);
                    b.offsetMin = new Vector2(-2, 12);
                    b.offsetMax = new Vector2(2, -12);
                }
                else
                {
                    b.anchorMin = new Vector2(0, 0.5f);
                    b.anchorMax = new Vector2(1, 0.5f);
                    b.offsetMin = new Vector2(11, -2);
                    b.offsetMax = new Vector2(-11, 2);
                }
            }
        }

        Dropdown NewDropdown(RectTransform root, string name)
        {
            root.name = name;
            var bg = Pill(root, Glass, raycast: true);
            Edge(root, WithAlpha(Cyan, 0.35f));
            var dd = root.gameObject.AddComponent<Dropdown>();
            dd.targetGraphic = bg;

            var label = Txt("Label", root, 13, TextMain, TextAnchor.MiddleLeft);
            Stretch(label.rectTransform);
            label.rectTransform.offsetMin = new Vector2(18, 0);
            label.rectTransform.offsetMax = new Vector2(-18, 0);
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            dd.captionText = label;

            var template = Rect("Template", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 1f), Vector2.zero, new Vector2(0, 220));
            template.anchorMin = new Vector2(0, 0);
            template.anchorMax = new Vector2(1, 0);
            Rounded(template, new Color(0.05f, 0.12f, 0.19f, 0.98f), 14, raycast: true);
            var scroll = template.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            var viewport = Rect("Viewport", template, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(viewport);
            viewport.gameObject.AddComponent<RectMask2D>();
            var content = Rect("Content", viewport, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), Vector2.zero, new Vector2(0, 40));
            content.anchorMin = new Vector2(0, 1);
            content.anchorMax = new Vector2(1, 1);
            scroll.viewport = viewport;
            scroll.content = content;

            var item = Rect("Item", content, new Vector2(0.5f, 0.5f), Center, Vector2.zero, new Vector2(0, 40));
            item.anchorMin = new Vector2(0, 0.5f);
            item.anchorMax = new Vector2(1, 0.5f);
            var toggle = item.gameObject.AddComponent<Toggle>();
            var itemBg = Img(item, null, new Color(1, 1, 1, 0.06f), raycast: true, child: true);
            toggle.targetGraphic = itemBg;
            var check = Rect("Item Checkmark", item, new Vector2(0, 0.5f), Center, new Vector2(14, 0), new Vector2(8, 9));
            toggle.graphic = Img(check, "hex", Cyan);
            var itemLabel = Txt("Item Label", item, 13, TextMain, TextAnchor.MiddleLeft);
            Stretch(itemLabel.rectTransform);
            itemLabel.rectTransform.offsetMin = new Vector2(28, 0);
            itemLabel.horizontalOverflow = HorizontalWrapMode.Overflow;

            dd.template = template;
            dd.itemText = itemLabel;
            template.gameObject.SetActive(false);
            return dd;
        }
    }

    /// 9 分割の丸を、いつも短い辺の半分の半径（カプセル）で描く
    sealed class PillRadius : MonoBehaviour
    {
        Image _image;
        float _last = -1;

        void OnEnable()
        {
            _image = GetComponent<Image>();
            Apply();
        }

        void OnRectTransformDimensionsChange() => Apply();

        void Apply()
        {
            if (_image == null) return;
            var r = ((RectTransform)transform).rect;
            var radius = Mathf.Max(1f, Mathf.Min(r.width, r.height) / 2);
            if (Mathf.Approximately(radius, _last)) return;
            _last = radius;
            _image.pixelsPerUnitMultiplier = 63f / radius;
        }
    }

    /// 押しているあいだ少し縮む。長押し（Hold）とタップ（Click）を分けて受け取ることもできる
    sealed class PressScale : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IPointerExitHandler, IPointerClickHandler
    {
        public Action Click, Hold;
        float _downAt = -1;
        bool _held;

        public void OnPointerDown(PointerEventData e)
        {
            _downAt = Time.unscaledTime;
            _held = false;
            transform.localScale = Vector3.one * 0.95f;
        }

        public void OnPointerUp(PointerEventData e) => Release();
        public void OnPointerExit(PointerEventData e) => Release();

        void Release()
        {
            _downAt = -1;
            transform.localScale = Vector3.one;
        }

        public void OnPointerClick(PointerEventData e)
        {
            if (!_held) Click?.Invoke();
        }

        void Update()
        {
            if (_downAt < 0 || _held || Hold == null) return;
            if (Time.unscaledTime - _downAt < 0.45f) return;
            _held = true;
            Release();
            Hold();
        }
    }

    /// 端末の切り欠き・ホームのバーを除いた範囲（Screen.safeArea）に合わせる
    sealed class SafeArea : MonoBehaviour
    {
        Rect _last;
        Vector2Int _screen;

        void Update()
        {
            var area = Screen.safeArea;
            var screen = new Vector2Int(Screen.width, Screen.height);
            if (area == _last && screen == _screen) return;
            _last = area;
            _screen = screen;
            var r = (RectTransform)transform;
            r.anchorMin = new Vector2(area.xMin / screen.x, area.yMin / screen.y);
            r.anchorMax = new Vector2(area.xMax / screen.x, area.yMax / screen.y);
            r.offsetMin = r.offsetMax = Vector2.zero;
        }
    }
}
