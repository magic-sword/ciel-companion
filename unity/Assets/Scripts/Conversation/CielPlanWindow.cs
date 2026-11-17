using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    // 計画グラフ（plan v1）を別のウィンドウに映す。表示だけで、操作は送らない（選び直しは言葉で頼む）。
    // 列は依存の深さ、行は同じ深さの節。節の下に、その節で進めている段と選択を並べる。
    public sealed class CielPlanWindow : MonoBehaviour
    {
        public const int Layer = 28;
        public static bool FocusCurrent { get => PlayerPrefs.GetInt("ciel.planGraph.focus", 1) == 1;
            set { PlayerPrefs.SetInt("ciel.planGraph.focus", value ? 1 : 0); PlayerPrefs.Save(); } }
        public CielStreamWindow Output { get; private set; }
        CielConversation _conversation;
        Canvas _canvas;
        RectTransform _board, _edges;
        Text _title, _note, _empty;
        Font _font;
        string _shown;
        readonly Dictionary<string, RectTransform> _boxes = new Dictionary<string, RectTransform>();

        static readonly Color Back = new Color(0.027f, 0.11f, 0.15f, 1);
        static readonly Color Ink = new Color(0.94f, 0.98f, 1);
        static readonly Color Dim = new Color(0.62f, 0.72f, 0.78f);
        const float ColumnWidth = 440, ColumnGap = 70, BoxGap = 18, LineHeight = 34;
        // The board in the canvas' reference units (1280 x 720 less the title and margins), so the
        // fit does not depend on when Unity lays the canvas out.
        static readonly Vector2 BoardSize = new Vector2(960, 710);

        static Color StateColor(string state) => state switch {
            "running" => new Color(0.5f, 0.91f, 1),
            "waiting_choice" => new Color(1, 0.77f, 0.42f),
            "done" => new Color(0.45f, 0.78f, 0.55f),
            "failed" => new Color(1, 0.45f, 0.45f),
            "ready" => new Color(0.85f, 0.9f, 0.95f),
            _ => new Color(0.45f, 0.52f, 0.58f) };

        void Awake()
        {
            _conversation = FindAnyObjectByType<CielConversation>();
            if (Camera.main != null) Camera.main.cullingMask &= ~(1 << Layer);
            var source = new GameObject("Plan Source Camera", typeof(Camera));
            source.transform.SetParent(transform, false);
            var camera = source.GetComponent<Camera>();
            camera.enabled = false;
            camera.orthographic = true;
            camera.cullingMask = 1 << Layer;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Back;
            camera.depth = -21;
            var output = new GameObject("Plan Graph Output", typeof(CielStreamWindow));
            output.transform.SetParent(source.transform, false);
            Output = output.GetComponent<CielStreamWindow>();
            Output.ConfigureCard(camera, CielStreamWindow.PlanTitle, "CielPlanGraphWindow", "ciel.planGraph", new Vector2Int(1552, 873));
            Build(camera);
        }

        void Build(Camera camera)
        {
            var go = new GameObject("PlanGraphCanvas", typeof(Canvas), typeof(CanvasScaler));
            go.transform.SetParent(transform, false);
            _canvas = go.GetComponent<Canvas>();
            _canvas.renderMode = RenderMode.ScreenSpaceCamera;
            _canvas.worldCamera = camera;
            _canvas.planeDistance = 1;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1552, 873);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;
            _font = Font.CreateDynamicFontFromOSFont(new[] { "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP" }, 64);
            var root = (RectTransform)go.transform;
            var bg = Box("Back", root, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            bg.gameObject.AddComponent<Image>().color = Back;
            _title = Label("Title", root, 34, Ink, new Vector2(0, 1), Vector2.one, new Vector2(40, -70), new Vector2(-552, -20));
            _title.fontStyle = FontStyle.Bold;
            _note = Label("Note", root, 20, Dim, new Vector2(0, 1), Vector2.one, new Vector2(40, -134), new Vector2(-552, -72));
            _board = Box("Board", root, Vector2.zero, Vector2.one, new Vector2(40, 23), new Vector2(-552, -140));
            _edges = Box("Edges", _board, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            _empty = Label("Empty", _board, 26, Dim, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            _empty.alignment = TextAnchor.MiddleCenter;
            SetLayer(go);
            Show(new CielPlanPresentation());
        }

        static RectTransform Box(string name, Transform parent, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = (RectTransform)go.transform;
            r.anchorMin = min; r.anchorMax = max;
            r.offsetMin = offsetMin; r.offsetMax = offsetMax;
            return r;
        }

        Text Label(string name, RectTransform parent, int size, Color color, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
        {
            var text = Box(name, parent, min, max, offsetMin, offsetMax).gameObject.AddComponent<Text>();
            text.font = _font;
            text.fontSize = size;
            text.color = color;
            text.supportRichText = false;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            text.raycastTarget = false;
            return text;
        }

        static void SetLayer(GameObject go)
        {
            go.layer = Layer;
            foreach (Transform child in go.transform) SetLayer(child.gameObject);
        }

        void Clear()
        {
            foreach (var box in _boxes.Values) Destroy(box.gameObject);
            _boxes.Clear();
            foreach (Transform edge in _edges) Destroy(edge.gameObject);
        }

        public void Show(CielPlanPresentation p)
        {
            Clear();
            _empty.text = p.visible ? "" : "シエルの計画はまだありません";
            _title.text = p.visible ? "シエルの計画：" + p.title : "シエルの計画";
            _note.text = p.visible ? (string.IsNullOrEmpty(p.summary) ? p.note : p.summary + "　｜　" + p.note) : "";
            if (!p.visible) return;
            var tops = new Dictionary<int, float>();
            foreach (var node in p.nodes)
            {
                tops.TryGetValue(node.column, out var top);
                var box = NodeBox(node, node.column * (ColumnWidth + ColumnGap), top);
                tops[node.column] = top + box.sizeDelta.y + BoxGap;
                _boxes[node.id] = box;
            }
            // 全体が収まるように縮める（大きくはしない）
            var width = Mathf.Max(1, p.columns * (ColumnWidth + ColumnGap) - ColumnGap);
            var height = 1f;
            foreach (var t in tops.Values) height = Mathf.Max(height, t);
            var scale = Mathf.Min(1, BoardSize.x / width, BoardSize.y / height);
            foreach (var box in _boxes.Values) box.localScale = Vector3.one * scale;
            foreach (var box in _boxes.Values) box.anchoredPosition *= scale;
            foreach (var node in p.nodes)
                foreach (var need in node.needs)
                    if (_boxes.TryGetValue(need, out var from)) Edge(from, _boxes[node.id], scale);
            SetLayer(_board.gameObject);
        }

        RectTransform NodeBox(CielPlanPresentation.Node node, float x, float y)
        {
            var lines = 2 + node.children.Count + (node.hiddenDone > 0 ? 1 : 0) + (node.options.Length > 0 ? 1 : 0);
            foreach (var child in node.children) if (child.options.Length > 0) lines++;
            var height = 20 + lines * LineHeight;
            var box = Box(node.id, _board, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, Vector2.zero);
            box.pivot = new Vector2(0, 1);
            box.sizeDelta = new Vector2(ColumnWidth, height);
            box.anchoredPosition = new Vector2(x, -y);
            var color = StateColor(node.state);
            box.gameObject.AddComponent<Image>().color = new Color(0.06f, 0.17f, 0.23f, 1);
            var edge = Box("Accent", box, Vector2.zero, new Vector2(0, 1), Vector2.zero, new Vector2(node.current ? 8 : 4, 0));
            edge.gameObject.AddComponent<Image>().color = color;
            float line = 10;
            Text Row(string text, int size, Color c, float indent = 0)
            {
                var t = Label("Line", box, size, c, new Vector2(0, 1), Vector2.one, new Vector2(18 + indent, -line - LineHeight), new Vector2(-12, -line));
                t.horizontalOverflow = HorizontalWrapMode.Overflow;
                t.resizeTextForBestFit = true;
                t.resizeTextMinSize = 14;
                t.resizeTextMaxSize = size;
                t.text = text;
                line += LineHeight;
                return t;
            }
            Row(node.text, 26, Ink).fontStyle = FontStyle.Bold;
            Row(node.stateLabel + (string.IsNullOrEmpty(node.estimate) ? "" : "　" + node.estimate), 21, color);
            if (node.options.Length > 0)
                Row("候補：" + string.Join(" / ", node.options) + (string.IsNullOrEmpty(node.chosen) ? "" : "　→ " + node.chosen), 20, StateColor("waiting_choice"));
            if (node.hiddenDone > 0) Row($"完了した段 {node.hiddenDone}件", 19, Dim, 14);
            foreach (var child in node.children)
            {
                Row(child.text + "　" + child.stateLabel + (string.IsNullOrEmpty(child.chosen) ? "" : "　→ " + child.chosen), 20, StateColor(child.state), 14);
                if (child.options.Length > 0) Row("候補：" + string.Join(" / ", child.options), 19, StateColor(child.state), 34);
            }
            return box;
        }

        // 前提の節の右端から、この節の左端へ線を引く
        void Edge(RectTransform from, RectTransform to, float scale)
        {
            var a = from.anchoredPosition + new Vector2(ColumnWidth * scale, -27 * scale);
            var b = to.anchoredPosition + new Vector2(0, -27 * scale);
            var line = Box("Edge", _edges, new Vector2(0, 1), new Vector2(0, 1), Vector2.zero, Vector2.zero);
            line.pivot = new Vector2(0, 0.5f);
            line.anchoredPosition = a;
            var d = b - a;
            line.sizeDelta = new Vector2(d.magnitude, 3);
            line.localRotation = Quaternion.Euler(0, 0, Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg);
            line.gameObject.AddComponent<Image>().color = new Color(0.5f, 0.91f, 1, 0.45f);
        }

        void Update()
        {
            if (_conversation == null) return;
            var connected = _conversation.Status == CielConversation.State.Connected;
            var p = connected ? CielPlanPresentation.From(_conversation.Goal, FocusCurrent) : new CielPlanPresentation();
            // 描き直すのは計画の版か新しさが変わったときだけ
            var key = p.visible ? p.key : "none";
            if (key != _shown)
            {
                _shown = key;
                Show(p);
            }
            if (Output.StreamCamera != null) _canvas.worldCamera = Output.StreamCamera;
        }
    }
}
