// 会話の画面（CielConversationUI）のうち、設定画面（下からすべり出る）。
// タブ：声と会話（シエルの声の大きさ・おしゃべり度・その場にいる人）、背景（CielBackground）、
// 議事録（送り先の Discord の Webhook を足す・消す・選ぶ。この端末の中に持つ）、
// 配信（Windows では配信用のウィンドウとその背景（グリーンバックなど）、YouTube のコメントを受け取る（CielConversation.YouTube.cs））、そのほか（PC では声のつなぎ方（ふだん・会議）と
// マイクとスピーカー（CielConversationUI.Route.cs）、
// マイクラで一緒に遊ぶ（CielConversation.Game.cs）、開発：開発用のサーバーにつなぐ・表情の確認ボタン）。
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
        Image _exprSwitch, _exprKnob, _devServerSwitch, _devServerKnob, _streamSwitch, _streamKnob, _gameSwitch, _gameKnob;
        Text _gameNow, _youtubeNow;
        readonly List<(Image fill, Image edge, Text label)> _backdropSegs = new List<(Image, Image, Text)>();
        Image _youtubeSwitch, _youtubeKnob;
        InputField _youtubeUrl;
        RectTransform _destList;
        InputField _destName, _destUrl;
        Text _destError;
        int _destRevision = -1;

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
                ("議事録", BuildMinutesSection),
                ("配信", c => { BuildStreamSection(c); BuildYouTubeSection(c); }),
                ("そのほか", c => { BuildDevicesSection(c); BuildGameSection(c); BuildDevSection(c); }),
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

        // 議事録の送り先（Discord の Webhook）。選んだものへ下書きを送る。声でも「議事録は〇〇に送って」と切り替えられる
        void BuildMinutesSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "議事録の送り先");
            _destList = Section(sec);
            Note(sec, "選んでいる送り先へ、議事録などのまとめの下書きを送ります。声でも「議事録は〇〇に送って」と切り替えられます。"
                + "登録しなければ、サーバーの既定の送り先へ送ります（無ければサーバーに保存します）");

            var add = Section(content);
            SectionLabel(Row(add, 20), "送り先を足す");
            _destName = NameField(Row(add, 40), "", 0, "名前（例：仕事）", CielConversation.MaxMinutesDestinationName);
            _destUrl = NameField(Row(add, 40), "", 0, "Webhook の URL", 200);
            _destUrl.keyboardType = TouchScreenKeyboardType.URL;
            var button = PanelButton(Row(add, 40), "足す", TextAnchor.MiddleCenter);
            button.onClick.AddListener(() =>
            {
                _destError.text = _conversation.AddMinutesDestination(_destName.text, _destUrl.text) ?? "";
                if (_destError.text.Length == 0) _destName.text = _destUrl.text = "";
            });
            _destError = Txt("Error", add, 11, Amber, TextAnchor.UpperLeft);
            Note(add, "Discord のチャンネルの設定 → 連携サービス → ウェブフック で作った URL を貼ります。"
                + "利用者だけが見るチャンネルにしてください。送り先はこの端末にだけ保存し、会話サーバーには送るためだけに渡します");
        }

        // 送り先の一覧（変わったときだけ作り直す）。押すと選び、右の「消す」で消す
        void RefreshMinutesDestinations()
        {
            var c = _conversation;
            if (_destRevision == c.MinutesDestinationsRevision) return;
            _destRevision = c.MinutesDestinationsRevision;
            foreach (Transform child in _destList) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            var items = c.MinutesDestinations;
            var selected = c.SelectedMinutesDestination;
            if (items.Count == 0)
            {
                var none = Txt("None", Row(_destList, 24), 13, TextSub, TextAnchor.MiddleLeft);
                Stretch(none.rectTransform);
                none.text = "まだありません（サーバーの既定の送り先へ送ります）";
                return;
            }
            foreach (var d in items)
            {
                var name = d.name;
                var sel = name == selected;
                var row = Row(_destList, 44);
                var hit = Rounded(row, sel ? WithAlpha(CyanDeep, 0.22f) : new Color(1f, 1f, 1f, 0.05f), 10, raycast: true);
                Edge(row, sel ? Cyan : WithAlpha(Cyan, 0.25f));
                var mark = Rect("Mark", row, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(22, 0), new Vector2(20, 20));
                Img(mark, sel ? "circle" : "circle_outline", sel ? CyanDeep : WithAlpha(Cyan, 0.5f));
                if (sel) Icon(mark, "check", 11, Ink);
                var label = Txt("Name", row, 14, sel ? TextMain : TextSub, TextAnchor.MiddleLeft, sel);
                label.supportRichText = false;
                label.horizontalOverflow = HorizontalWrapMode.Overflow;
                Stretch(label.rectTransform);
                label.rectTransform.offsetMin = new Vector2(42, 0);
                label.rectTransform.offsetMax = new Vector2(-76, 0);
                label.text = name;
                var b = row.gameObject.AddComponent<Button>();
                b.targetGraphic = hit;
                b.transition = Selectable.Transition.None;
                b.onClick.AddListener(() => c.SelectMinutesDestination(name));
                var remove = Rect("Remove", row, new Vector2(1, 0.5f), new Vector2(1, 0.5f), new Vector2(-6, 0), new Vector2(62, 32));
                remove.pivot = new Vector2(1, 0.5f);
                PanelButton(remove, "消す", TextAnchor.MiddleCenter).onClick.AddListener(() => c.RemoveMinutesDestination(name));
            }
        }

        // PC（Windows）だけ：配信用のウィンドウ（CielStreamWindow）
        void BuildStreamSection(RectTransform content)
        {
            if (_stream == null) return;
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "配信");
            (_streamSwitch, _streamKnob) = SwitchRow(sec, "配信用のウィンドウを開く", () => _stream.SetOpen(!_stream.IsOpen));
            BuildStreamGoalSwitch(sec);   // いまの目的の札（CielConversationUI.Goal.cs）
            Note(sec, $"シエルと背景だけを映すウィンドウ「{CielStreamWindow.Title}」を開きます。"
                + "OBS のウィンドウキャプチャでこちらを取り込むと、設定・名前・ボタンは映りません。大きさを変えると、その大きさで描きます");

            var bg = Section(content);
            SectionLabel(Row(bg, 20), "配信の背景");
            Segmented(bg, CielStreamWindow.BackdropLabels, i => _stream.SetBackdrop((CielStreamWindow.Backdrop)i), _backdropSegs);
            Note(bg, "グリーンバック・ブルーバックは、配信用のウィンドウだけを一色にします（アプリの画面は「背景」タブの絵のまま）。"
                + "OBS でウィンドウキャプチャを右クリック →「フィルタ」→「クロマキー」を足し、同じ色を選ぶと背景が透けます");
        }

        // YouTube の配信のコメント（CielConversation.YouTube.cs）。読むのは会話サーバー（API キーも会話サーバー）
        void BuildYouTubeSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "YouTube のコメント");
            _youtubeUrl = NameField(Row(sec, 40), _conversation.YouTubeUrl, 0, "配信の URL（例：https://youtube.com/live/…）", 200);
            _youtubeUrl.keyboardType = TouchScreenKeyboardType.URL;
            _youtubeUrl.onEndEdit.AddListener(url => _conversation.SetYouTube(url, _conversation.YouTube && url.Trim().Length > 0));
            (_youtubeSwitch, _youtubeKnob) = SwitchRow(sec, "コメントを受け取って返す",
                () => _conversation.SetYouTube(_youtubeUrl.text, !_conversation.YouTube));
            _youtubeNow = Txt("Now", sec, 12, TextMain, TextAnchor.UpperLeft, true);
            Note(sec, "配信の URL（視聴ページ・共有の URL・YouTube Studio の配信の画面の URL）を貼ってスイッチを入れると、"
                + "シエルがコメントを読み、話の切れ目に返します（話している人の声が先です）。スーパーチャットは先に読みます。"
                + "ログインは要りません。公開・限定公開の配信だけ読めます。配信の前に入れておくと、始まるのを待ちます");
        }

        static string YouTubeNow(CielConversation c)
        {
            if (!c.YouTube) return "";
            if (c.Status != CielConversation.State.Connected) return "いまは：つないだら、配信のコメントを受け取ります";
            var title = c.YouTubeTitle.Length > 0 ? $"「{c.YouTubeTitle}」" : "配信";
            switch (c.YouTubeState)
            {
                case "": return "いまは：会話サーバーの返事を待っています（古い会話サーバーは対応していません）";
                case "connecting": return "いまは：配信につないでいます…";
                case "waiting": return $"いまは：{title}が始まるのを待っています";
                case "live": return $"いまは：● {title}のコメントを受け取っています（届いた {c.YouTubeReceived} 件・返した {c.YouTubeReplied} 件）";
                case "off": return "いまは：止めています";
            }
            switch (c.YouTubeReason)
            {
                case "bad_url": return "いまは：URL から配信が分かりませんでした。視聴ページの URL を貼ってください";
                case "no_key": return "いまは：会話サーバーに YouTube の API キーがありません（server/agent/.env の YOUTUBE_API_KEY）";
                case "not_found": return "いまは：動画が見つかりません（非公開の配信は読めません）";
                case "not_live": return "いまは：この動画は配信ではありません";
                case "not_started": return "いまは：配信が始まりませんでした。始まってからスイッチを入れ直してください";
                case "liveChatEnded": return "いまは：配信のチャットが終わりました";
                case "liveChatDisabled": return "いまは：この配信はチャットがオフです";
                case "quotaExceeded": return "いまは：今日の YouTube API の上限に達しました（日本時間の 16〜17 時に戻ります）";
                case "keyInvalid": case "badRequest": return "いまは：会話サーバーの YouTube の API キーが使えません";
            }
            return $"いまは：配信につなげませんでした（{c.YouTubeReason}）";
        }

        // マイクラで一緒に遊ぶ（CielConversation.Game.cs。docs/minecraft-design-ja.md）
        void BuildGameSection(RectTransform content)
        {
            var sec = Section(content);
            SectionLabel(Row(sec, 20), "マイクラ");
            (_gameSwitch, _gameKnob) = SwitchRow(sec, "マイクラで一緒に遊ぶ", () => _conversation.SetMinecraft(!_conversation.Minecraft));
            _gameNow = Txt("Now", sec, 12, TextMain, TextAnchor.UpperLeft, true);
            Note(sec, "自宅サーバーのマイクラの世界にいるシエルの体とつなぎ、声で「ついてきて」「木を集めて」と頼めるようにします。"
                + "体を動かせるのは、一度に 1 つの会話だけです");
        }

        static string GameNow(CielConversation c)
        {
            if (!c.Minecraft) return "";
            if (c.Status != CielConversation.State.Connected) return "いまは：つないだら、シエルの体とつなぎます";
            if (!c.GameKnown) return "いまは：会話サーバーがマイクラに対応していません";
            if (c.GameLinked) return c.GameInWorld ? "いまは：● シエルはマイクラの中にいます" : "いまは：体とつながりました（マイクラに入るのを待っています）";
            return c.GameReason == "busy" ? "いまは：ほかの会話がシエルの体を使っています"
                : c.GameReason == "unavailable" ? "いまは：この会話サーバーはマイクラにつなげません"
                : "いまは：シエルの体へつないでいます…";
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
            RefreshRoute();   // 声のつなぎ方とマイク・スピーカー（CielConversationUI.Route.cs）
            var expr = ExpressionButtonsOn;
            if (_exprPanel != null) _exprPanel.SetActive(expr);
            ShowSwitch(_exprSwitch, _exprKnob, expr);
            ShowSwitch(_devServerSwitch, _devServerKnob, c.DevServer);
            ShowSwitch(_gameSwitch, _gameKnob, c.Minecraft);
            _gameNow.text = GameNow(c);
            if (_stream != null)
            {
                ShowSwitch(_streamSwitch, _streamKnob, _stream.IsOpen);
                ShowSelected(_backdropSegs, (int)_stream.CurrentBackdrop);
            }
            ShowSwitch(_youtubeSwitch, _youtubeKnob, c.YouTube);
            _youtubeNow.text = YouTubeNow(c);
            if (!_youtubeUrl.isFocused && _youtubeUrl.text != c.YouTubeUrl) _youtubeUrl.SetTextWithoutNotify(c.YouTubeUrl);
            RefreshStreamGoalSwitch();
            RefreshMinutesDestinations();
        }

        static void RefreshDevices(Dropdown dd, List<string> guids, bool can, List<(string name, string guid)> devices,
            string selected, string defaultName, string prefix)
        {
            dd.gameObject.SetActive(can);
            if (!can) return;
            var names = new List<string> { prefix + defaultName };
            foreach (var (name, _) in devices) names.Add(prefix + name);
            // 機器が増減したときと、つなぎ方を変えて呼び名が変わったときに作り直す
            if (guids.Count != devices.Count + 1 || dd.options.Count != names.Count || dd.options[0].text != names[0]
                || (names.Count > 1 && dd.options[1].text != names[1]))
            {
                guids.Clear();
                dd.ClearOptions();
                guids.Add(null);
                foreach (var (_, guid) in devices) guids.Add(guid);
                dd.AddOptions(names);
            }
            dd.SetValueWithoutNotify(Mathf.Max(0, guids.IndexOf(selected)));
        }

        // 設定の出し入れ（下からすべり出る。Update から呼ぶ）
        void UpdateSheet()
        {
            if (_sheetOpen) UpdateMeetingCheck();
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
