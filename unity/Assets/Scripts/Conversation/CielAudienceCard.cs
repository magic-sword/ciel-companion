using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    // 表示だけの出力。会話接続・音声・モデルは追加しない。
    public sealed class CielAudienceCard : MonoBehaviour
    {
        public const int Layer = 29;
        public CielStreamWindow Output { get; private set; }
        CielConversation _conversation;
        Canvas _canvas;
        GameObject _panel;
        Text _heading, _title, _current, _progress;
        Image _bar, _accent;

        void Awake()
        {
            _conversation = FindAnyObjectByType<CielConversation>();
            if (Camera.main != null) Camera.main.cullingMask &= ~(1 << Layer);
            var source = new GameObject("Card Source Camera", typeof(Camera));
            source.transform.SetParent(transform, false);
            var camera = source.GetComponent<Camera>();
            camera.enabled = false;
            camera.orthographic = true;
            camera.cullingMask = 1 << Layer;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.green;
            camera.depth = -20;
            var output = new GameObject("Audience Card Output", typeof(CielStreamWindow));
            output.transform.SetParent(source.transform, false);
            Output = output.GetComponent<CielStreamWindow>();
            Output.ConfigureCard(camera);
            Build(camera);
        }

        void Build(Camera camera)
        {
            var go = new GameObject("AudienceCardCanvas", typeof(Canvas), typeof(CanvasScaler));
            go.transform.SetParent(transform, false);
            _canvas = go.GetComponent<Canvas>();
            _canvas.renderMode = RenderMode.ScreenSpaceCamera;
            _canvas.worldCamera = camera;
            _canvas.planeDistance = 1;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(900, 500);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;
            var panel = Box("Card", go.transform, new Vector2(0, 0), new Vector2(1, 1), Vector2.zero, Vector2.zero);
            _panel = panel.gameObject;
            panel.gameObject.AddComponent<Image>().color = new Color(0.027f, 0.11f, 0.15f, 1);
            _accent = Box("Accent", panel, Vector2.zero, Vector2.up, new Vector2(0, 32), new Vector2(6, -32)).gameObject.AddComponent<Image>();
            _accent.color = new Color(0.5f, 0.91f, 1);
            var font = Font.CreateDynamicFontFromOSFont(new[] { "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP" }, 64);
            _heading = Label("Heading", panel, font, 42, 38, 30, 50);
            _title = Label("Title", panel, font, 64, 38, 100, 140);
            _title.fontStyle = FontStyle.Bold;
            _title.resizeTextForBestFit = true;
            _title.resizeTextMinSize = 36;
            _title.resizeTextMaxSize = 64;
            _current = Label("Current", panel, font, 46, 38, 258, 98);
            _progress = Label("Progress", panel, font, 38, 38, 385, 55);
            var track = Box("ProgressTrack", panel, new Vector2(0, 0), new Vector2(1, 0), new Vector2(38, 24), new Vector2(-38, 34));
            track.gameObject.AddComponent<Image>().color = new Color(0.14f, 0.25f, 0.3f);
            _bar = Box("ProgressFill", track, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero).gameObject.AddComponent<Image>();
            _bar.color = new Color(0.5f, 0.91f, 1);
            SetLayer(go);
            _panel.SetActive(false);
        }

        // offsetMin/Maxを明示し、カメラの比率が変わっても画面の内側へ収める。
        static RectTransform Box(string name, Transform parent, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = (RectTransform)go.transform;
            r.anchorMin = min; r.anchorMax = max;
            r.offsetMin = offsetMin; r.offsetMax = offsetMax;
            return r;
        }

        static Text Label(string name, RectTransform panel, Font font, int size, float left, float top, float height)
        {
            var rect = Box(name, panel, new Vector2(0, 1), Vector2.one, new Vector2(left, -top - height), new Vector2(-38, -top));
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.color = new Color(0.94f, 0.98f, 1);
            text.supportRichText = false;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            text.raycastTarget = false;
            return text;
        }

        static void SetLayer(GameObject go)
        {
            go.layer = Layer;
            foreach (Transform child in go.transform) SetLayer(child.gameObject);
        }

        public void Show(CielAudienceCardState state)
        {
            _panel.SetActive(state.visible);
            if (!state.visible) return;
            _heading.text = state.heading;
            _title.text = state.title;
            _current.text = string.IsNullOrEmpty(state.current) ? "" : "いま：" + state.current;
            _progress.text = state.progress;
            var color = state.attention ? new Color(1, 0.77f, 0.42f) : new Color(0.5f, 0.91f, 1);
            _accent.color = _bar.color = color;
            _bar.transform.parent.gameObject.SetActive(state.fraction >= 0);
            _bar.rectTransform.anchorMax = new Vector2(Mathf.Clamp01(state.fraction), 1);
        }

        void Update()
        {
            if (_conversation == null) return;
            var recent = Time.unscaledTime - _conversation.GoalSince < 8;
            Show(CielAudienceCardState.From(_conversation.Goal, _conversation.Activity,
                _conversation.Status == CielConversation.State.Connected, recent));
            if (Output.StreamCamera != null) _canvas.worldCamera = Output.StreamCamera;
        }
    }
}
