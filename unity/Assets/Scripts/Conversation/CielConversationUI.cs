// 会話の画面の操作：マイクボタン（タップで入れる・切る）、状態の表示、PC ではマイクの選択。
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
        Text _micLabel, _status;
        Dropdown _devices;
        readonly List<string> _deviceGuids = new List<string>();
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

            // マイクの選択（PC だけ。画面の上）
            _devices = NewDropdown(canvasGo.transform);
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

            _devices.gameObject.SetActive(c.CanSelectMic);
            if (c.CanSelectMic && _deviceGuids.Count != c.MicDevices.Count + 1)
            {
                _deviceGuids.Clear();
                _devices.ClearOptions();
                var names = new List<string> { "既定のマイク（OS の設定）" };
                _deviceGuids.Add(null);
                foreach (var (name, guid) in c.MicDevices) { names.Add(name); _deviceGuids.Add(guid); }
                _devices.AddOptions(names);
            }
            if (c.CanSelectMic)
                _devices.SetValueWithoutNotify(Mathf.Max(0, _deviceGuids.IndexOf(c.SelectedMic)));
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

        Dropdown NewDropdown(Transform parent)
        {
            // uGUI の標準のドロップダウンと同じ構成を作る
            var root = NewRect("MicDevice", parent, new Vector2(0.5f, 1f), new Vector2(0, -80), new Vector2(900, 80));
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
