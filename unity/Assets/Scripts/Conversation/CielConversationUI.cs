// 会話の画面の操作：マイクボタン（タップで入れる・切る）、状態の表示、会話のモード、PC ではマイクとスピーカーの選択、
// Android では声をスピーカーから出すか受話口から出すかの切り替え。
// 画面の部品は実行時にコードで作る（シーンに置くのは、このコンポーネントだけ）。
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

        static readonly Color MicOff = new Color(0.20f, 0.24f, 0.36f, 0.92f);
        static readonly Color MicOn = new Color(0.93f, 0.33f, 0.40f, 0.95f);
        static readonly Color MicBusy = new Color(0.55f, 0.55f, 0.60f, 0.92f);

        Image _micImage;
        Text _micLabel, _status, _modeLabel, _speakerphoneLabel;
        GameObject _speakerphone;
        Dropdown _devices, _speakers;
        readonly List<string> _deviceGuids = new List<string>();
        readonly List<string> _speakerGuids = new List<string>();
        Font _font;

        void Awake()
        {
            if (_conversation == null) _conversation = FindAnyObjectByType<CielConversation>();
            _font = Font.CreateDynamicFontFromOSFont(
                new[] { "Yu Gothic UI", "Meiryo UI", "Meiryo", "Hiragino Sans", "Noto Sans CJK JP", "Noto Sans JP" }, 32);
            Build();
        }

        void OnEnable() { if (_conversation != null) _conversation.Changed += Refresh; Refresh(); }
        void OnDisable() { if (_conversation != null) _conversation.Changed -= Refresh; }

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
            scaler.referenceResolution = new Vector2(1080, 1920);
            scaler.matchWidthOrHeight = 0.5f;

            // マイクボタン（画面の下の中央、丸）
            var mic = NewRect("MicButton", canvasGo.transform, new Vector2(0.5f, 0f), new Vector2(0, 170), new Vector2(220, 220));
            _micImage = mic.gameObject.AddComponent<Image>();
            _micImage.sprite = Circle();
            var button = mic.gameObject.AddComponent<Button>();
            button.onClick.AddListener(() => _conversation.SetMicEnabled(!_conversation.MicEnabled));
            _micLabel = NewText("Label", mic, 40, TextAnchor.MiddleCenter);
            Stretch(_micLabel.rectTransform);

            // 状態の表示（ボタンの上）
            _status = NewText("Status", canvasGo.transform, 34, TextAnchor.MiddleCenter);
            var sr = _status.rectTransform;
            sr.anchorMin = sr.anchorMax = new Vector2(0.5f, 0f);
            sr.anchoredPosition = new Vector2(0, 330);
            sr.sizeDelta = new Vector2(1000, 60);
            var shadow = _status.gameObject.AddComponent<Shadow>();
            shadow.effectColor = new Color(0, 0, 0, 0.6f);

            // 表情の確認用のボタン（画面の右。表情を作りながら確かめる）
            BuildExpressionButtons(canvasGo.transform);

            // 会話のモードの切り替え（タップで 自動 → 2 人 → 多人数 → 自動）。下の欄の一覧より奥に出るよう、先に作る
            var mode = NewRect("ModeButton", canvasGo.transform, new Vector2(0.5f, 1f), new Vector2(0, -260), new Vector2(900, 70));
            mode.gameObject.AddComponent<Image>().color = new Color(0.12f, 0.14f, 0.22f, 0.85f);
            mode.gameObject.AddComponent<Button>().onClick.AddListener(() =>
                _conversation.SelectMode((CielConversation.ModeSetting)(((int)_conversation.ModeChoice + 1) % 3)));
            _modeLabel = NewText("Label", mode, 30, TextAnchor.MiddleCenter);
            Stretch(_modeLabel.rectTransform);

            // Android：声を本体のスピーカーから出すか（PC の機器の選択欄の場所。Android では選択欄は出ない）
            var sp = NewRect("SpeakerphoneButton", canvasGo.transform, new Vector2(0.5f, 1f), new Vector2(0, -170), new Vector2(900, 70));
            sp.gameObject.AddComponent<Image>().color = new Color(0.12f, 0.14f, 0.22f, 0.85f);
            sp.gameObject.AddComponent<Button>().onClick.AddListener(() => _conversation.SetSpeakerphone(!_conversation.SpeakerphoneOn));
            _speakerphoneLabel = NewText("Label", sp, 30, TextAnchor.MiddleCenter);
            Stretch(_speakerphoneLabel.rectTransform);
            _speakerphone = sp.gameObject;

            // マイクとスピーカーの選択（PC だけ。画面の上）。下の欄を先に作り、上の欄の一覧が下の欄より手前に出るようにする
            _speakers = NewDropdown(canvasGo.transform, "SpeakerDevice", -170);
            _speakers.onValueChanged.AddListener(i => _conversation.SelectSpeaker(i <= 0 ? null : _speakerGuids[i]));
            _devices = NewDropdown(canvasGo.transform, "MicDevice", -80);
            _devices.onValueChanged.AddListener(i => _conversation.SelectMic(i <= 0 ? null : _deviceGuids[i]));
        }

        void Refresh()
        {
            if (_micImage == null || _conversation == null) return;
            var c = _conversation;
            var connected = c.Status == CielConversation.State.Connected;
            _micImage.color = !connected || c.MicBusy ? MicBusy : c.MicEnabled ? MicOn : MicOff;
            _micLabel.text = c.MicEnabled ? "録音中\n（タップで止める）" : "マイク\n（タップで話す）";
            _micImage.GetComponent<Button>().interactable = connected && !c.MicBusy;
            _status.text = c.Status switch
            {
                CielConversation.State.Connecting => "シエルに接続しています…",
                CielConversation.State.Failed => "接続できませんでした",
                CielConversation.State.Disconnected => "接続していません",
                _ => c.MicEnabled ? "話しかけてください" : "マイクを入れると話せます",
            };

            var current = c.CurrentMode == CielConversation.Mode.Group ? "多人数（呼ばれたら答える）" : "2 人（いつも答える）";
            _modeLabel.text = c.ModeChoice == CielConversation.ModeSetting.Auto ? $"会話：自動 ― いまは {current}" : $"会話：{current}";
            _speakerphone.SetActive(c.CanUseSpeakerphone);
            _speakerphoneLabel.text = c.SpeakerphoneOn ? "声：スピーカー（みんなに聞こえる）" : "声：受話口（耳に当てて聞く）";

            RefreshDevices(_devices, _deviceGuids, c.CanSelectMic, c.MicDevices, c.SelectedMic, "既定のマイク（OS の設定）", "マイク：");
            RefreshDevices(_speakers, _speakerGuids, c.CanSelectSpeaker, c.SpeakerDevices, c.SelectedSpeaker, "既定のスピーカー（OS の設定）", "声の出力：");
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

        [SerializeField] bool _showExpressionButtons = true;

        void BuildExpressionButtons(Transform canvas)
        {
            if (!_showExpressionButtons) return;
            var expression = FindAnyObjectByType<CielExpression>();
            if (expression == null) return;
            var names = CielExpression.Names;
            for (int i = 0; i < names.Length; i++)
            {
                var n = names[i];
                var r = NewRect("Expr_" + n, canvas, new Vector2(1f, 1f), new Vector2(-110, -200 - i * 78), new Vector2(190, 66));
                var img = r.gameObject.AddComponent<Image>();
                img.color = new Color(0.12f, 0.14f, 0.22f, 0.8f);
                r.gameObject.AddComponent<Button>().onClick.AddListener(() => expression.Set(n, 4f));
                var t = NewText("Label", r, 28, TextAnchor.MiddleCenter);
                Stretch(t.rectTransform);
                t.text = CielExpression.JapaneseNames[n];
            }
        }

        // ---- 画面の部品 ----

        static RectTransform NewRect(string name, Transform parent, Vector2 anchor, Vector2 pos, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = (RectTransform)go.transform;
            r.anchorMin = r.anchorMax = anchor;
            r.anchoredPosition = pos;
            r.sizeDelta = size;
            return r;
        }

        static void Stretch(RectTransform r)
        {
            r.anchorMin = Vector2.zero;
            r.anchorMax = Vector2.one;
            r.offsetMin = r.offsetMax = Vector2.zero;
        }

        Text NewText(string name, Transform parent, int size, TextAnchor align)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Text));
            go.transform.SetParent(parent, false);
            var t = go.GetComponent<Text>();
            t.font = _font;
            t.fontSize = size;
            t.alignment = align;
            t.color = Color.white;
            t.raycastTarget = false;
            return t;
        }

        Dropdown NewDropdown(Transform parent, string name, float y)
        {
            // uGUI の標準のドロップダウンと同じ構成を作る
            var root = NewRect(name, parent, new Vector2(0.5f, 1f), new Vector2(0, y), new Vector2(900, 80));
            var bg = root.gameObject.AddComponent<Image>();
            bg.color = new Color(0.12f, 0.14f, 0.22f, 0.85f);
            var dd = root.gameObject.AddComponent<Dropdown>();

            var label = NewText("Label", root, 32, TextAnchor.MiddleLeft);
            Stretch(label.rectTransform);
            label.rectTransform.offsetMin = new Vector2(24, 0);
            dd.captionText = label;

            var template = NewRect("Template", root, new Vector2(0.5f, 0f), Vector2.zero, new Vector2(0, 400));
            template.anchorMin = new Vector2(0, 0);
            template.anchorMax = new Vector2(1, 0);
            template.pivot = new Vector2(0.5f, 1f);
            template.gameObject.AddComponent<Image>().color = new Color(0.10f, 0.12f, 0.18f, 0.97f);
            var scroll = template.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            var viewport = NewRect("Viewport", template, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(viewport);
            viewport.gameObject.AddComponent<RectMask2D>();
            var content = NewRect("Content", viewport, new Vector2(0.5f, 1f), Vector2.zero, new Vector2(0, 80));
            content.anchorMin = new Vector2(0, 1);
            content.anchorMax = new Vector2(1, 1);
            content.pivot = new Vector2(0.5f, 1f);
            scroll.viewport = viewport;
            scroll.content = content;

            var item = NewRect("Item", content, new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(0, 80));
            item.anchorMin = new Vector2(0, 0.5f);
            item.anchorMax = new Vector2(1, 0.5f);
            var toggle = item.gameObject.AddComponent<Toggle>();
            var itemBg = NewRect("Item Background", item, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(itemBg);
            var itemBgImage = itemBg.gameObject.AddComponent<Image>();
            itemBgImage.color = new Color(1, 1, 1, 0.08f);
            toggle.targetGraphic = itemBgImage;
            var check = NewRect("Item Checkmark", item, new Vector2(0, 0.5f), new Vector2(24, 0), new Vector2(12, 40));
            var checkImage = check.gameObject.AddComponent<Image>();
            checkImage.color = MicOn;
            toggle.graphic = checkImage;
            var itemLabel = NewText("Item Label", item, 30, TextAnchor.MiddleLeft);
            Stretch(itemLabel.rectTransform);
            itemLabel.rectTransform.offsetMin = new Vector2(48, 0);

            dd.template = template;
            dd.itemText = itemLabel;
            template.gameObject.SetActive(false);
            return dd;
        }

        static Sprite _circle;

        static Sprite Circle()
        {
            if (_circle != null) return _circle;
            const int n = 128;
            var tex = new Texture2D(n, n, TextureFormat.RGBA32, false);
            var c = (n - 1) / 2f;
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    var d = Mathf.Sqrt((x - c) * (x - c) + (y - c) * (y - c));
                    tex.SetPixel(x, y, new Color(1, 1, 1, Mathf.Clamp01(c - d + 0.5f)));
                }
            tex.Apply();
            _circle = Sprite.Create(tex, new Rect(0, 0, n, n), new Vector2(0.5f, 0.5f));
            return _circle;
        }
    }
}
