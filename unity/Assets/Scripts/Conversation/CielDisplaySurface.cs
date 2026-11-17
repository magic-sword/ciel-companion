using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    // Shared, display-only camera/canvas plumbing. Views own their content and state.
    public sealed class CielDisplaySurface
    {
        public CielStreamWindow Output { get; }
        public Canvas Canvas { get; }
        public RectTransform Root => (RectTransform)Canvas.transform;
        readonly Camera _source;
        readonly int _layer;

        public CielDisplaySurface(Transform parent, string cameraName, string outputName, string canvasName,
            int layer, float depth, Color background, string title, string windowClass, string prefs, Vector2Int size)
        {
            _layer = layer;
            if (Camera.main != null) Camera.main.cullingMask &= ~(1 << layer);
            var source = new GameObject(cameraName, typeof(Camera));
            source.transform.SetParent(parent, false);
            _source = source.GetComponent<Camera>();
            _source.enabled = false;
            _source.orthographic = true;
            _source.cullingMask = 1 << layer;
            _source.clearFlags = CameraClearFlags.SolidColor;
            _source.backgroundColor = background;
            _source.depth = depth;
            var output = new GameObject(outputName, typeof(CielStreamWindow));
            output.transform.SetParent(source.transform, false);
            Output = output.GetComponent<CielStreamWindow>();
            Output.ConfigureCard(_source, title, windowClass, prefs, size);
            var go = new GameObject(canvasName, typeof(Canvas), typeof(CanvasScaler));
            go.transform.SetParent(parent, false);
            Canvas = go.GetComponent<Canvas>();
            Canvas.renderMode = RenderMode.ScreenSpaceCamera;
            Canvas.worldCamera = _source;
            Canvas.planeDistance = 1;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = size;
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.Expand;
        }

        // Restore the source camera when the native output closes; it may open again.
        public void BindCamera() => Canvas.worldCamera = Output.StreamCamera != null ? Output.StreamCamera : _source;
        public void SetLayer(GameObject root)
        {
            root.layer = _layer;
            foreach (Transform child in root.transform) SetLayer(child.gameObject);
        }

        public static RectTransform Box(string name, Transform parent, Vector2 min, Vector2 max, Vector2 offsetMin, Vector2 offsetMax)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var rect = (RectTransform)go.transform;
            rect.anchorMin = min; rect.anchorMax = max;
            rect.offsetMin = offsetMin; rect.offsetMax = offsetMax;
            return rect;
        }
    }
}
