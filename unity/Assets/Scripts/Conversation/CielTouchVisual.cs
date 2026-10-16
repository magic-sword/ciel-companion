// シエルに触れている点の表示。CielTouch のイベントを受けて、会話の画面（CielConversationUI が作る層）に描く。
// 見た目は企画設計の「シエル主観視界」の決まりに合わせる：シアンの細い光の縁、角の丸い六角（Ciel Prism の形）、
// 選ぶときは光が外から中心へ集まる、呼吸するような弱い明滅、共感は淡い琥珀色。赤（危険の色）や照準のような形は使わない。
// シエルの体は白いので、光を足して白くする描き方はせず、濃いシアンを重ね、下に薄い紺のにじみを敷いて見分けやすくする。
//   触れ始め：光の輪が外から指先へ縮まって集まる。反応しない部位では、暗いシアンの細い輪が一瞬出るだけ
//   長く触れる：六角の輪が tap とみなす長さで一周して満ち、そのあとは呼吸するように明滅する
//   なぞる：指の後ろに先細りの光の軌跡。なぞりと判定されると明るくなり、撫でる強さに合わせて琥珀色へ寄る
//   離す：tap は輪が広がりながら六角へ変わって消える波紋、ほかは光がふわっと消える
// 寸法は会話の画面と同じモックアップ（390×844）の単位。
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    public sealed class CielTouchVisual : MonoBehaviour
    {
        static readonly Color CyanDeep = new Color32(0x2C, 0xC8, 0xEE, 255), Cyan = new Color32(0x7F, 0xE9, 0xFF, 255);
        static readonly Color Ink = new Color32(0x04, 0x29, 0x3D, 255);
        // 共感の琥珀色。白い体の上でも見えるよう、会話の画面の琥珀（#FFC46B）より少し深くする
        static readonly Color AmberDeep = new Color32(0xF0, 0xA8, 0x45, 255);

        const float RingSize = 36f, CoreSize = 26f, HaloSize = 72f, DotSize = 22f, DotHaloSize = 40f;
        static readonly Vector2 HexSize = new Vector2(44f, 48.6f);   // 画像（152×168）と同じ縦横比
        const float Converge = 0.22f;      // 光が集まる時間（秒）
        const float Breath = 1.6f;         // 明滅の周期（秒）
        const float FadeOut = 0.25f;       // 離したあと消える時間（秒）
        const float TrailLife = 0.4f;      // 軌跡が消える時間（秒）
        const float TrailSpacing = 3f;     // 軌跡の点の間隔

        CielTouch _touch;
        RectTransform _layer, _trailHalo, _trail, _effects;

        // 触れている点
        RectTransform _contact;
        Image _halo, _core, _ring, _hex;
        bool _touching, _stroking, _visible;
        float _age, _releaseAge, _strokeAge, _travel;
        Vector2 _pos, _lastDot, _lastScreen;

        // 消えていく表示（軌跡の点・波紋）
        enum Fade { Out, Trail, Swell }   // Out：だんだん消える、Trail：軌跡（一定の速さで消える）、Swell：ふくらんでから消える
        sealed class Fx
        {
            public Image Img;
            public float Age, Life, From, To, Alpha;
            public Color Color;
            public Fade Fade;
        }
        readonly List<Fx> _fx = new List<Fx>();
        readonly Dictionary<string, Stack<Image>> _pool = new Dictionary<string, Stack<Image>>();

        public void Init(CielTouch touch, RectTransform layer)
        {
            _touch = touch;
            _layer = layer;
            _trailHalo = Layer("TrailHalo");
            _trail = Layer("Trail");
            _contact = Layer("Contact");
            _effects = Layer("Effects");
            _contact.anchorMin = _contact.anchorMax = new Vector2(0.5f, 0.5f);
            _contact.sizeDelta = Vector2.zero;
            _halo = NewImage("glow", _contact, Vector2.one * HaloSize);
            _core = NewImage("glow", _contact, Vector2.one * CoreSize);
            _ring = NewImage("touch_ring", _contact, Vector2.one * RingSize);
            _hex = NewImage("hex_ring", _contact, HexSize);
            _hex.type = Image.Type.Filled;
            _hex.fillMethod = Image.FillMethod.Radial360;
            _hex.fillOrigin = (int)Image.Origin360.Top;
            _hex.fillClockwise = true;
            _contact.gameObject.SetActive(false);

            _touch.Pressed += OnPressed;
            _touch.Dragged += OnDragged;
            _touch.StrokeStarted += OnStrokeStarted;
            _touch.Released += OnReleased;
        }

        void OnDestroy()
        {
            if (_touch == null) return;
            _touch.Pressed -= OnPressed;
            _touch.Dragged -= OnDragged;
            _touch.StrokeStarted -= OnStrokeStarted;
            _touch.Released -= OnReleased;
        }

        // ---- イベント ----

        void OnPressed(Vector2 screen, CielTouch.Part part)
        {
            var p = Local(screen);
            if (part == CielTouch.Part.None)
            {
                // 反応しない部位：触れたことだけを伝える
                Spawn("touch_ring", _effects, p, Vector2.one * 26f, 1f, 1.3f, 0.35f, 0.6f, Color.Lerp(CyanDeep, Ink, 0.4f), Fade.Out);
                return;
            }
            _touching = _visible = true;
            _stroking = false;
            _age = _travel = 0;
            _pos = _lastDot = p;
            _lastScreen = screen;
            _contact.gameObject.SetActive(true);
        }

        void OnDragged(Vector2 screen)
        {
            if (!_touching) return;
            _travel += (screen - _lastScreen).magnitude / Screen.height;
            _lastScreen = screen;
            _pos = Local(screen);
            // 前の点から指の位置まで、間を空けて点を置く
            var d = _pos - _lastDot;
            var n = Mathf.FloorToInt(d.magnitude / TrailSpacing);
            for (int i = 1; i <= n; i++)
            {
                var at = _lastDot + d * (i * TrailSpacing / d.magnitude);
                Spawn("glow", _trailHalo, at, Vector2.one * DotHaloSize, 1f, 0.5f, TrailLife, _stroking ? 0.14f : 0.07f, Ink, Fade.Trail);
                Spawn("glow", _trail, at, Vector2.one * DotSize, 1f, 0.3f, TrailLife, _stroking ? 0.9f : 0.45f, Tint(), Fade.Trail);
            }
            if (n > 0) _lastDot += d * (n * TrailSpacing / d.magnitude);
        }

        void OnStrokeStarted()
        {
            _stroking = true;
            _strokeAge = 0;
        }

        void OnReleased(string gesture)
        {
            if (!_touching) return;
            _touching = false;
            _releaseAge = 0;
            if (gesture != "tap") return;
            // 波紋：丸い輪が広がりながら、六角の輪へ移り変わって消える
            _releaseAge = FadeOut;   // 触れていた光はすぐ消す
            Spawn("touch_ring", _effects, _pos, Vector2.one * RingSize, 1f, 2.2f, 0.35f, 0.85f, CyanDeep, Fade.Out);
            Spawn("hex_ring", _effects, _pos, HexSize, 0.85f, 2.0f, 0.4f, 0.75f, CyanDeep, Fade.Swell);
        }

        // ---- 毎フレーム ----

        void Update()
        {
            var dt = Time.unscaledDeltaTime;
            UpdateContact(dt);
            for (int i = _fx.Count - 1; i >= 0; i--)
            {
                var f = _fx[i];
                f.Age += dt;
                var k = f.Age / f.Life;
                if (k >= 1f)
                {
                    Release(f.Img);
                    _fx.RemoveAt(i);
                    continue;
                }
                var ease = 1f - (1f - k) * (1f - k);
                f.Img.rectTransform.localScale = Vector3.one * Mathf.Lerp(f.From, f.To, ease);
                var a = f.Fade == Fade.Out ? (1f - k) * (1f - k) : f.Fade == Fade.Trail ? 1f - k : Mathf.Sin(Mathf.PI * k);
                f.Img.color = WithAlpha(f.Color, f.Alpha * a);
            }
        }

        void UpdateContact(float dt)
        {
            if (!_visible) return;
            _age += dt;
            _strokeAge += dt;
            var fade = 1f;
            var swell = 1f;
            if (!_touching)
            {
                _releaseAge += dt;
                var k = Mathf.Clamp01(_releaseAge / FadeOut);
                fade = 1f - k;
                swell = 1f + 0.15f * k;
                if (k >= 1f)
                {
                    _visible = false;
                    _contact.gameObject.SetActive(false);
                    return;
                }
            }
            _contact.anchoredPosition = _pos;

            // 光が外から集まる → 呼吸するように明滅する
            var p = Mathf.Clamp01(_age / Converge);
            var e = 1f - (1f - p) * (1f - p) * (1f - p);
            var breath = Mathf.Lerp(1f, 0.85f + 0.15f * Mathf.Cos(2f * Mathf.PI * (_age - Converge) / Breath), p);
            // なぞりと判定された瞬間に、少しふくらんで明るくなる
            var pop = _stroking ? 1f + 0.25f * (1f - Mathf.Clamp01(_strokeAge / 0.25f)) : 1f;
            var tint = Tint();

            _ring.rectTransform.localScale = Vector3.one * (Mathf.Lerp(2.4f, 1f, e) * pop * swell);
            _ring.color = WithAlpha(tint, 0.9f * e * breath * fade);
            _core.rectTransform.localScale = Vector3.one * (Mathf.Lerp(0.4f, 1f, e) * pop);
            _core.color = WithAlpha(tint, (_stroking ? 0.7f : 0.55f) * e * breath * fade);
            _halo.color = WithAlpha(Ink, (_stroking ? 0.3f : 0.22f) * e * fade);

            // 長く触れる：少し待ってから六角の輪が満ちていく。指が動き始めたら（なぞりになりそうなら）消す
            var tap = Mathf.Max(_touch.TapTime, 0.15f);
            var fill = Mathf.Clamp01((_age - 0.1f) / (tap - 0.1f));
            var still = Mathf.Clamp01(1f - (_travel - 0.01f) / 0.01f);
            _hex.fillAmount = fill;
            _hex.rectTransform.localScale = Vector3.one * swell;
            var hexBreath = fill < 1f ? 1f : 0.75f + 0.25f * Mathf.Cos(2f * Mathf.PI * (_age - tap) / Breath);
            _hex.color = WithAlpha(Color.Lerp(CyanDeep, Cyan, 0.2f), 0.75f * hexBreath * still * fade * (_stroking ? 0f : 1f));
        }

        // 撫でる強さに合わせて、シアンから琥珀色（共感の色）へ寄る
        Color Tint() => Color.Lerp(CyanDeep, AmberDeep, _touch != null ? _touch.StrokeAmount : 0f);

        // ---- 部品 ----

        Vector2 Local(Vector2 screen)
        {
            RectTransformUtility.ScreenPointToLocalPointInRectangle(_layer, screen, null, out var p);
            return p;
        }

        RectTransform Layer(string name)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(_layer, false);
            var r = (RectTransform)go.transform;
            r.anchorMin = Vector2.zero;
            r.anchorMax = Vector2.one;
            r.offsetMin = r.offsetMax = Vector2.zero;
            return r;
        }

        static Image NewImage(string sprite, RectTransform parent, Vector2 size)
        {
            var go = new GameObject(sprite, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(parent, false);
            var img = go.GetComponent<Image>();
            img.sprite = Resources.Load<Sprite>("CielUI/" + sprite);
            if (img.sprite == null) Debug.LogWarning($"[CielTouchVisual] 画像 CielUI/{sprite} がない");
            img.raycastTarget = false;   // 表示がタッチの判定を邪魔しない
            img.rectTransform.sizeDelta = size;
            return img;
        }

        void Spawn(string sprite, RectTransform parent, Vector2 pos, Vector2 size, float from, float to, float life, float alpha, Color color, Fade fade)
        {
            var img = _pool.TryGetValue(sprite, out var stack) && stack.Count > 0 ? stack.Pop() : NewImage(sprite, parent, size);
            var r = img.rectTransform;
            r.SetParent(parent, false);
            r.SetAsLastSibling();
            r.anchorMin = r.anchorMax = new Vector2(0.5f, 0.5f);
            r.sizeDelta = size;
            r.anchoredPosition = pos;
            r.localScale = Vector3.one * from;
            img.color = WithAlpha(color, 0f);
            img.gameObject.SetActive(true);
            _fx.Add(new Fx { Img = img, Life = life, From = from, To = to, Alpha = alpha, Color = color, Fade = fade });
        }

        void Release(Image img)
        {
            img.gameObject.SetActive(false);
            var name = img.gameObject.name;
            if (!_pool.TryGetValue(name, out var stack)) _pool[name] = stack = new Stack<Image>();
            stack.Push(img);
        }

        static Color WithAlpha(Color c, float a) => new Color(c.r, c.g, c.b, a);
    }
}
