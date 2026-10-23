// 会話の画面（A案「シエルの視界」）。デザインは CIEL Companion UI案のキャンバス（A案・設定・その場で音量）。
// 下の中央に Ciel Prism の形のマイクボタン、左にまとめ（議事録など）、右に声の出力（Android はタップでスピーカー・受話口、
// 長押しで声の大きさ。PC はタップで声の大きさ）。上に接続の状態、会話のモード、設定のボタン。
// 設定画面：シエルの声の大きさ、背景（CielBackground）、会話のしかた、PC ではマイクとスピーカー、開発用の表情の確認ボタン。
// シエルに触れている点の表示（CielTouchVisual）は、画面の暗がりとボタンの間の層に描く。
// 画面の部品は実行時にコードで作る（シーンに置くのは、このコンポーネントだけ）。
// このファイルはふだんの画面。設定画面は CielConversationUI.Settings.cs、調べたこと・出典は CielConversationUI.Research.cs、
// 参加者の札と名前の直しは CielConversationUI.People.cs、会話のまとめ（議事録など）は CielConversationUI.Summary.cs、
// 部品を作る道具は CielConversationUI.Parts.cs、部品に付ける動きは CielUIComponents.cs。
// 寸法はモックアップ（390×844）の値。上下の位置は、端末の切り欠きを除いた範囲（Screen.safeArea）から測る。
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    public sealed partial class CielConversationUI : MonoBehaviour
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

        Font _font;
        RectTransform _canvasRect, _safe;

        // 上
        Image _linkDot;
        Text _linkText, _modeText, _nameText;
        RectTransform _modeChip;
        // 声の様子と状態
        readonly List<RectTransform> _bars = new List<RectTransform>();
        readonly List<Image> _barImages = new List<Image>();
        Text _status, _caption, _activity;
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
        // 開発用の表情の確認ボタン
        GameObject _exprPanel;

        void Awake()
        {
            if (_conversation == null) _conversation = FindAnyObjectByType<CielConversation>();
            if (_background == null) _background = FindAnyObjectByType<CielBackground>();
            if (_background == null) _background = gameObject.AddComponent<CielBackground>();
            if (FindAnyObjectByType<CielResizeGuard>() == null) gameObject.AddComponent<CielResizeGuard>();   // 画面の大きさが変わってもシエルを描く
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
            BuildTouchLayer(_canvasRect);
            _safe = Rect("SafeArea", _canvasRect, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(_safe);
            _safe.gameObject.AddComponent<SafeArea>();

            BuildTop(_safe);
            BuildExpressionButtons(_safe);
            BuildVoiceStatus(_safe);
            BuildBottomRow(_safe);
            BuildVolumePop(_canvasRect);
            BuildSheet(_canvasRect);
            BuildResearch(_safe);
            BuildPeople(_safe);
            BuildSummary(_safe);
        }

        // シエルに触れている点の表示（CielTouchVisual）。暗がりの上、ボタンや文字の下に描く
        void BuildTouchLayer(RectTransform root)
        {
            var touch = FindAnyObjectByType<CielTouch>();
            if (touch == null) return;
            var layer = Rect("Touch", root, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(layer);
            gameObject.AddComponent<CielTouchVisual>().Init(touch, layer);
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
            _nameText = Txt("Name", root, 13, TextMain, TextAnchor.UpperLeft, true);
            _nameText.text = "C I E L";
            Place(_nameText.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(24, -12), new Vector2(150, 20));

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

            // 会話のしかた：おしゃべり度・いまのその場にいる人（タップで ひかえめ → ふつう → おしゃべり → ひかえめ）
            var mode = Rect("ModeButton", root, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-64, -6), new Vector2(150, 36));
            _modeChip = mode;
            var mb = Pill(mode, Glass, raycast: true);
            Edge(mode, WithAlpha(Cyan, 0.55f));
            var icon = Icon(mode, "talk", 14, Cyan);
            Place(icon.rectTransform, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(21, 0), new Vector2(14, 14));
            _modeText = Txt("Text", mode, 12, TextMain, TextAnchor.MiddleLeft);
            Place(_modeText.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(34, 0), new Vector2(140, 20));
            _modeText.horizontalOverflow = HorizontalWrapMode.Overflow;
            var modeButton = mode.gameObject.AddComponent<Button>();
            modeButton.targetGraphic = mb;
            modeButton.onClick.AddListener(() =>
                _conversation.SelectTalk((CielConversation.Talk)(((int)_conversation.TalkChoice + 1) % 3)));
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

            // 裏で進んでいること（まとめを作っている・話しながら調べている）。声の様子のすぐ上に細く
            _activity = Txt("Activity", root, 12, Amber, TextAnchor.MiddleCenter);
            _activity.supportRichText = false;
            Place(_activity.rectTransform, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 216), new Vector2(360, 18));
            var activityShadow = _activity.gameObject.AddComponent<Shadow>();
            activityShadow.effectColor = new Color(0, 0.08f, 0.16f, 0.8f);
            activityShadow.effectDistance = new Vector2(0, -1f);
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
            _minutesButton.onClick.AddListener(() => ShowSummary(!_summaryPanel.activeSelf));
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
            // 外を押したら閉じる。つまみの親ではなく兄弟に置く（親に置くと、つまみを触っただけで閉じてしまう）
            var blockerRect = Rect("Blocker", pop, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(blockerRect);
            var blocker = Img(blockerRect, null, Color.clear, raycast: true);
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
            RefreshResearch();
            RefreshPeople();
            RefreshSummary();
            if (_micHex == null || _conversation == null) return;
            var c = _conversation;
            var connected = c.Status == CielConversation.State.Connected;

            (_linkDot.color, _linkText.text) = c.Status switch
            {
                CielConversation.State.Connecting => (Amber, "つないでいます…"),
                CielConversation.State.Failed => (Alert, "つながらない・タップで再試行"),
                CielConversation.State.Disconnected => (Idle, "未接続・タップでつなぐ"),
                _ => (Mint, "つながっています"),
            };
            _linkDot.transform.GetChild(0).GetComponent<Image>().color = WithAlpha(_linkDot.color, 0.6f);
            // 開発用のサーバーにつないでいることを、いつも見えるように（左上の名前の横）
            _nameText.text = c.DevServer ? "C I E L ・ 開発用" : "C I E L";
            _nameText.color = c.DevServer ? Amber : TextMain;

            var talk = (int)c.CurrentTalk;
            var presence = (int)c.CurrentPresence;
            _modeText.text = $"{TalkLabels[talk]}・{PresenceLabels[presence]}";
            _modeChip.sizeDelta = new Vector2(34 + _modeText.preferredWidth + 14, 36);

            UpdateStatusLine();

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
            _minutesLabel.text = rec ? "記録中" : "まとめ";
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

            RefreshSettings();
        }

        // 会話サーバーが返事を考えている（返事を頼んでから、声が出るまで）
        static bool Thinking(CielConversation c) => c.Thinking;

        // シエルの状態（マイクの上）と、裏で進んでいること（声の様子の上）。利用者の声やシエルの声の始まり・終わりでも変わるので、
        // 毎フレーム見る（変わったときだけ書き換える）。上から順に優先する：
        // 話しています（声が出ている）→ 調べています（Web で調べている）→ 考えています（返事を頼んでから声が出るまで）
        // → 聞いています（利用者の声が届いている）→ 話しかけてください
        void UpdateStatusLine()
        {
            var c = _conversation;
            var connected = c.Status == CielConversation.State.Connected;
            var speaking = connected && c.AgentState == "speaking";
            var research = connected && c.ResearchPending;
            var listening = connected && c.MicEnabled && c.UserSpeaking;
            var (status, caption) = c.Status switch
            {
                CielConversation.State.Connecting => ("シエルに接続しています…", ""),
                CielConversation.State.Failed => ("接続できませんでした", ""),
                CielConversation.State.Disconnected => ("接続していません", ""),
                _ when speaking => ("話しています", "S P E A K I N G"),
                _ when research => ("調べています…", "S E A R C H I N G"),
                _ when Thinking(c) => ("考えています…", "T H I N K I N G"),   // 聞き終えて、返事を考えている（声が出るまでの間も、聞こえたと分かるように）
                _ when listening => ("聞いています…", "L I S T E N I N G"),
                _ => (c.MicEnabled ? "話しかけてください" : "マイクを入れると話せます", c.MicEnabled ? "L I S T E N I N G" : ""),
            };
            if (_status.text != status) _status.text = status;
            if (_caption.text != caption) _caption.text = caption;
            var activity = connected && c.Summarizing ? c.Summary.label + "をまとめています…" : "";
            if (research && speaking)   // 話しながら調べているときは、裏のこととして出す
                activity = activity == "" ? "調べています…" : activity + "・調べています…";
            if (_activity.text != activity) _activity.text = activity;
        }

        // ---- 動き ----

        bool _firstRefresh;
        float _userLevel;   // 波形の高さ（自分の声が届いていると 1 へ近づく）

        void Update()
        {
            if (_conversation == null) return;
            // CielConversation は保存した設定（モード・声の大きさ）を Start で読むので、全部の Start のあとに表示を合わせる
            if (!_firstRefresh) { _firstRefresh = true; Refresh(); }
            UpdateStatusLine();   // 声の始まり・終わり、考えていたのが時間切れで終わったときも、すぐ表示に出す
            var t = Time.unscaledTime;
            var c = _conversation;
            var on = c.MicEnabled && c.Status == CielConversation.State.Connected;
            UpdatePeople();
            UpdateSummary();

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

            // マイクの様子：自分の声が届いている間だけ波が立つ（シエルの声には反応しない）
            var target = c.UserSpeaking ? 1f : 0f;
            _userLevel = Mathf.MoveTowards(_userLevel, target, Time.unscaledDeltaTime / (target > _userLevel ? 0.12f : 0.35f));
            var level = _userLevel;
            var thinking = Thinking(c);
            for (int i = 0; i < _bars.Count; i++)
            {
                var env = Mathf.Sin(Mathf.PI * (i + 0.5f) / _bars.Count);
                float h;
                if (level > 0.02f)
                {
                    // 声らしく不規則に揺れるよう、速さの違う波を重ねる
                    var w = Mathf.Abs(Mathf.Sin(t * 9f + i * 1.3f)) * 0.6f + Mathf.Abs(Mathf.Sin(t * 13.7f - i * 2.1f)) * 0.4f;
                    h = 3 + 15 * level * env * (0.3f + 0.7f * w);
                }
                else if (thinking)
                {
                    // 考えている間：光の粒が左から右へ流れる（1.1 秒ごとに 1 回）
                    var x = Mathf.Repeat(t / 1.1f, 1f) * (_bars.Count + 4) - 2;
                    h = 3 + 7 * Mathf.Exp(-(i - x) * (i - x) / 3f);
                }
                else if (on) h = 3 + 6 * env * (0.5f + 0.5f * Mathf.Sin(t * 3f + i * 0.7f));
                else h = 3;
                _bars[i].sizeDelta = new Vector2(3, h);
                _barImages[i].color = WithAlpha(Cyan, level > 0.02f || on || thinking ? 1f : 0.35f);
            }

            UpdateSheet();
        }
    }
}
