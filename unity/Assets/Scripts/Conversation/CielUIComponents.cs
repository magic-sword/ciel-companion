// 会話の画面（CielConversationUI）の部品に付ける小さな動き：カプセルの角、押したときの縮み・長押し、端末の安全な範囲。
using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Ciel.Conversation
{
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
        const float LongPress = 0.45f;   // 長押しとみなす秒数

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
            if (Time.unscaledTime - _downAt < LongPress) return;
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
