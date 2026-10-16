// シエルの後ろの背景。設定画面で選んだ絵（Assets/Resources/CielUI/Backgrounds）を、画面いっぱいに切り抜いて映す。
// 選んだ背景は PlayerPrefs に覚える。いまの絵は仮置き（scripts/ui/make_ui_sprites.py が企画設計の絵から作る）。
// 絵は、カメラの前の奥に置いた板（SpriteRenderer）に映す。当たり判定はないので、タッチ（CielTouch）を邪魔しない。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    public sealed class CielBackground : MonoBehaviour
    {
        public readonly struct Option
        {
            public readonly string Key, Label;
            public Option(string key, string label) { Key = key; Label = label; }
            public Sprite Load() => Resources.Load<Sprite>("CielUI/Backgrounds/" + Key);
        }

        public static readonly Option[] Options =
        {
            new Option("lounge", "テラスラウンジ"),
            new Option("garage_day", "工房（昼）"),
            new Option("garage_night", "工房（夜）"),
            new Option("plain", "無地"),
        };

        const string PrefKey = "ciel.background";

        public string Current { get; private set; }
        public event Action Changed;

        SpriteRenderer _renderer;
        Camera _camera;
        Vector3 _fitted;

        void Awake()
        {
            // シエル（Live2D）は URP の専用の描画（CubismRenderPassFeature）で、半透明の物より前に描かれる。
            // 背景は、それよりさらに前に描かれるよう、不透明の物の順番（Geometry）で描く。カメラの前の奥に置く
            _camera = Camera.main;
            var go = new GameObject("Background");
            go.transform.SetParent(_camera != null ? _camera.transform : transform, false);
            _renderer = go.AddComponent<SpriteRenderer>();
            var material = new Material(_renderer.sharedMaterial) { renderQueue = 2000 };
            _renderer.sharedMaterial = material;
            Set(PlayerPrefs.GetString(PrefKey, Options[0].Key));
        }

        // 画面の大きさ・向きが変わったら、画面いっぱいに切り抜き直す（足りない向きを広げる）
        void LateUpdate()
        {
            if (_camera == null || _renderer.sprite == null) return;
            var distance = Mathf.Min(_camera.farClipPlane * 0.5f, 50f);
            var height = _camera.orthographic ? _camera.orthographicSize * 2
                : 2 * distance * Mathf.Tan(_camera.fieldOfView * 0.5f * Mathf.Deg2Rad);
            var key = new Vector3(height, _camera.aspect, distance);
            if (key == _fitted) return;
            _fitted = key;
            var size = _renderer.sprite.bounds.size;
            var scale = Mathf.Max(height * _camera.aspect / size.x, height / size.y);
            var t = _renderer.transform;
            t.localPosition = new Vector3(0, 0, distance);
            t.localRotation = Quaternion.identity;
            t.localScale = new Vector3(scale, scale, 1);
        }

        public void Set(string key)
        {
            var option = Array.Find(Options, o => o.Key == key);
            if (option.Key == null) option = Options[0];
            var sprite = option.Load();
            if (sprite == null)
            {
                Debug.LogWarning($"[CielBackground] 背景 '{option.Key}' の絵がない");
                return;
            }
            Current = option.Key;
            PlayerPrefs.SetString(PrefKey, option.Key);
            _renderer.sprite = sprite;
            _fitted = Vector3.zero;
            Changed?.Invoke();
        }
    }
}
