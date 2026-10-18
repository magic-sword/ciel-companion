// シエルに触れる：画面のタップ・なぞりで、頭・耳・ほっぺ・髪・肩・手に触れたことを判定し、その場で体を反応させて、
// 会話サーバーへ知らせる（CielConversation.SendTouch。サーバーはシエルの声の反応を返す）。
//
// 判定：Cubism の当たり判定（CubismRaycaster）で触れた点に重なる部品を集め、絵の不透明な部分に触れている
//       部品のうち、いちばん手前のものを選ぶ（メッシュには透明な余白があり、余白だけでは触れたことにしない）。
//       胸・おなか・首などの部品は触れても反応せず、その奥の髪にも当たらない。
// しぐさ：短く触れる（tap）・なぞる（stroke）・長く触れたまま（hold）。なぞりは始まり（start）と終わり（end）、ほかは離したとき（once）に知らせる。
// 体の反応：目線を触れた点へ向け、頭を撫でられると頭が傾いて耳が下がる。触れた髪は物理演算の粒子を押して揺らし、
//           肩の毛皮はばねで揺らす。頭の傾きは物理演算の入力なので、髪も一緒に揺れる。
// ほっぺ：つつくと「ぷにっ」と押され（くぼみの影・赤み・その側の目を少し細める）、離すと物理演算で「ぷるん」と揺れる。
//         触れたまま指を動かすと、つまんで引っ張る（指についてくるが、伸びるほど重くなる）。離すと、ばねで揺れながら戻る。
//         やさしく引くと困り顔、強く・速く引くと半泣きになり、引っ張り（pull）として強さと表情をサーバーへ知らせる。
// 表情は CielExpression で短く切り替える（サーバーの返事が来れば、その表情に変わる）。
// 触れた点の表示は CielTouchVisual（このクラスのイベントを受け取る）。
using System;
using System.Collections.Generic;
using System.Reflection;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using Live2D.Cubism.Framework.Physics;
using Live2D.Cubism.Framework.Raycasting;
using Live2D.Cubism.Rendering;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem;

namespace Ciel.Conversation
{
    // シエルのモデル（CubismModel と同じ GameObject）に付ける
    public sealed class CielTouch : MonoBehaviour, ICubismUpdatable
    {
        public enum Part { None, Head, Ear, Face, Hair, Shoulder, Hand }

        [SerializeField] CubismModel _model;
        [SerializeField] CielExpression _expression;
        [SerializeField] CielConversation _conversation;
        [SerializeField] Camera _camera;
        [Tooltip("なぞりと判定する指の移動量（画面の高さに対する割合）")]
        [SerializeField] float _strokeDistance = 0.05f;
        [Tooltip("短く触れた（tap）とみなす長さ（秒）。これより長く動かさなければ hold")]
        [SerializeField] float _tapTime = 0.4f;
        [Tooltip("髪を指で押す強さ")]
        [SerializeField] float _hairPush = 6f;

        // 部品の名前の頭 → 触れた部位。上から順に調べる
        static readonly (string prefix, Part part)[] PartMap =
        {
            ("Ear_", Part.Ear),
            ("Hair_Crown", Part.Head), ("Hair_Front_", Part.Head), ("Hair_Ahoge", Part.Head),
            ("Hair_Side_", Part.Hair), ("Hair_Back", Part.Hair),
            ("Face_", Part.Face), ("Cheek_", Part.Face), ("Nose", Part.Face), ("Mouth_", Part.Face),
            ("Eye_", Part.Face), ("Brow_", Part.Face), ("Tear", Part.Face), ("Sweat", Part.Face),
            ("Jacket48_Fur_", Part.Shoulder), ("Jacket52_FurBack_", Part.Shoulder), ("Jacket48_SleeveUpper_", Part.Shoulder),
            ("Body48_Hand", Part.Hand), ("Body48_Forearm_", Part.Hand), ("Jacket48_SleeveLower_", Part.Hand),
            ("Jacket48_Cuff_", Part.Hand),
        };
        // 髪の部品 → 揺らす物理演算（出力のパラメーター）
        static readonly (string prefix, string output)[] HairPhysics =
        {
            ("Hair_Front_", "ParamHairFront"), ("Hair_Crown", "ParamHairFront"), ("Hair_Ahoge", "ParamHairFront"),
            ("Hair_Side_", "ParamHairSide"), ("Hair_Back", "ParamHairBack"),
        };

        // ---- 判定 ----
        CubismRaycaster _raycaster;
        readonly CubismRaycastHit[] _hits = new CubismRaycastHit[160];   // 重なる部品をすべて受け取る（足りないと手前の部品を見落とす）
        static readonly PropertyInfo OpacityProperty =
            typeof(CubismRenderer).GetProperty("Opacity", BindingFlags.Instance | BindingFlags.NonPublic);
        readonly Dictionary<string, CubismPhysicsSubRig> _hairRigs = new Dictionary<string, CubismPhysicsSubRig>();
        CubismDrawable _face;

        // ---- 今の触れ方 ----
        bool _pointerDown, _pressed, _stroking, _ignored;
        Part _part;
        string _drawable;
        float _pressTime, _travel;
        Vector2 _lastPos;
        float _sideX;   // 触れた点が顔の中心から左右どちらか（-1〜1、画面の右が正）

        // ---- 体の反応（パラメーターへ足す値） ----
        readonly Dictionary<string, CubismParameter> _params = new Dictionary<string, CubismParameter>();
        float _strokeAmount, _strokeSway;         // 撫でられている強さ（0〜1）、撫でる指の左右の動き
        Vector2 _gaze, _gazeTarget;               // 目線
        float _gazeWeight;
        readonly Spring _earTwitch = new Spring(), _headDip = new Spring(), _headTurn = new Spring(),
            _furL = new Spring(), _furR = new Spring();

        // ---- ほっぺ ----
        // くぼみの影の部品（顔と一緒に動く）を、ほっぺの位置の目印にする。L はモデルの左（画面の右）
        CubismDrawable _dimpleL, _dimpleR;
        const float DimpleGap = 392f;      // 左右のくぼみの間（キャンバスの画素）。画面の大きさをキャンバスの画素へ直すのに使う
        const float CheekLift = 46f, CheekRadius = 115f;   // ほっぺの中心（くぼみより少し上）と、ほっぺとみなす範囲（キャンバスの画素）
        const float PullStart = 0.012f;    // 指がこれだけ動いたら（画面の高さに対する割合）、押すのをやめて引っ張りにする
        const float PullUpLimit = -0.2f;   // 上向きの引っ張りの限度（ParamCielCheekPullY の負の側）
        const float PullReach = 110f;    // 指をこれだけ動かすと、引っ張りがほぼいっぱいになる（キャンバスの画素）
        int _cheek;                        // 触れているほっぺ：1 = L、-1 = R、0 = ほっぺではない
        bool _pokeHeld, _pulling;
        int _pokeSide = 1, _pullSide = 1;
        float _poke, _blush, _pullSpeed, _pullAmount;
        Vector2 _pullOrigin, _pullTarget, _pull, _pullVel;
        string _pullLevel = "", _pullFace = "";
        float _cheekUnit = 1f;             // 画面の 1 画素がキャンバスの何画素か

        public int ExecutionOrder => 750;   // 目線・揺れの後、物理演算（800）の前
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }

        /// 最後に判定した触れ方（確認用）
        public string LastTouch { get; private set; } = "";

        // 触れた点の表示（CielTouchVisual）へ知らせる。画面のボタンの上で触れたときは知らせない
        /// 触れ始めた点と部位（None は反応しない部位）
        public event Action<Vector2, Part> Pressed;
        /// 反応する部位に触れたまま指が動いた
        public event Action<Vector2> Dragged;
        /// なぞりと判定した
        public event Action StrokeStarted;
        /// 反応する部位から指を離した（tap・hold・stroke）
        public event Action<string> Released;
        /// 撫でられている強さ（0〜1）
        public float StrokeAmount => _strokeAmount;
        /// 短く触れた（tap）とみなす長さ（秒）
        public float TapTime => _tapTime;

        void Awake()
        {
            if (_model == null) _model = GetComponent<CubismModel>();
            if (_expression == null) _expression = GetComponent<CielExpression>();
            if (_conversation == null) _conversation = FindAnyObjectByType<CielConversation>();
            foreach (var p in _model.Parameters) _params[p.Id] = p;

            // 当たり判定：見える部品すべて（反応しない部品も、奥の部品へ触れさせないために判定する）
            _raycaster = GetComponent<CubismRaycaster>() ?? gameObject.AddComponent<CubismRaycaster>();
            foreach (var d in _model.Drawables)
            {
                if (d.GetComponent<CubismRaycastable>() != null) continue;
                d.gameObject.AddComponent<CubismRaycastable>().Precision = CubismRaycastablePrecision.Triangles;
                if (d.Id == "Face_Skin") _face = d;
                if (d.Id == "Cheek_Dimple_L") _dimpleL = d;
                if (d.Id == "Cheek_Dimple_R") _dimpleR = d;
            }
        }

        void Start()
        {
            HasUpdateController = GetComponent<CubismUpdateController>() != null;
            if (_camera == null) _camera = Camera.main;
            // 物理演算の髪の揺れ
            var physics = GetComponent<CubismPhysicsController>();
            var rig = physics == null ? null : (CubismPhysicsRig)typeof(CubismPhysicsController)
                .GetField("_rig", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(physics);
            if (rig != null)
                foreach (var sub in rig.SubRigs)
                    foreach (var o in sub.Output)
                        if (o.DestinationId.StartsWith("ParamHair")) _hairRigs[o.DestinationId] = sub;
            if (_hairRigs.Count == 0) Debug.LogWarning("[CielTouch] 髪の物理演算が見つからない");
        }

        // ---- 入力 ----

        void Update()
        {
            var pointer = UnityEngine.InputSystem.Pointer.current;
            if (pointer == null || _camera == null) return;
            var pos = pointer.position.ReadValue();
            var down = pointer.press.isPressed;
            if (down && !_pointerDown) Press(pos);
            else if (down) Drag(pos);
            else if (_pointerDown) Release();
            _pointerDown = down;
        }

        /// 画面の点で触れる部位（確認用）
        public Part PartAt(Vector2 screen) => Hit(screen).Item1;

        /// 画面の点に重なる部品（確認用）：名前、z、不透明度
        public string DescribeAt(Vector2 screen)
        {
            var count = _raycaster.Raycast(_camera.ScreenPointToRay(screen), _hits);
            var sb = new System.Text.StringBuilder($"{count} hits:");
            for (int i = 0; i < count; i++)
            {
                var r = _hits[i].Drawable.GetComponent<CubismRenderer>();
                sb.Append($" {_hits[i].Drawable.Id}(z={r.transform.position.z:0.0000},a={(float)OpacityProperty.GetValue(r):0.00},on={r.MeshRenderer.enabled})");
            }
            return sb.ToString();
        }

        /// 画面の点に触れ始める（確認用に外からも呼べる）
        public void Press(Vector2 screen)
        {
            _pressed = true;
            _stroking = false;
            _travel = 0;
            _pressTime = Time.time;
            _lastPos = screen;
            // 画面のボタンの上なら、シエルには触れない
            _ignored = OverUI(screen);
            if (_ignored) return;
            (_part, _drawable) = Hit(screen);
            _ignored = _part == Part.None;
            Pressed?.Invoke(screen, _part);
            if (_ignored) return;
            LookAt(screen);
            _sideX = SideOf(screen);
            if (_part == Part.Hair) PushHair(_drawable, _sideX >= 0 ? 0.6f : -0.6f);   // 触れた髪が少し揺れる
            _cheek = _part == Part.Face ? CheekAt(screen) : 0;
            if (_cheek != 0)
            {
                // ぷにっと押す。引っ張りが戻りきっていないうちに、反対のほっぺを押しても困らないよう、押す側だけを変える
                _pokeSide = _cheek;
                _pokeHeld = true;
                _pullOrigin = screen;
                _pullLevel = _pullFace = "";
            }
        }

        /// 画面の点が、どちらのほっぺか（1 = L、-1 = R、0 = ほっぺではない）
        public int CheekAt(Vector2 screen)
        {
            if (_dimpleL == null || _dimpleR == null) return 0;
            Vector2 l = _camera.WorldToScreenPoint(Center(_dimpleL)), r = _camera.WorldToScreenPoint(Center(_dimpleR));
            var gap = (l - r).magnitude;
            if (gap < 1f) return 0;
            _cheekUnit = DimpleGap / gap;
            // 画面の y は上向き。ほっぺの中心は、くぼみより少し上
            var lift = new Vector2(0, CheekLift / _cheekUnit);
            var dl = (screen - (l + lift)).magnitude * _cheekUnit;
            var dr = (screen - (r + lift)).magnitude * _cheekUnit;
            if (Mathf.Min(dl, dr) > CheekRadius) return 0;
            return dl <= dr ? 1 : -1;
        }

        // つまんで引っ張る：指の動きを、ほっぺの外向き・下向きの量へ直す。遠くへ引くほど重くなる（tanh）
        void DragCheek(Vector2 screen)
        {
            var starting = !_pulling && _travel >= PullStart;
            if (starting)
            {
                _pulling = true;
                _pokeHeld = false;   // 押していた形は離れ、物理演算で少し揺れる
                _pullSide = _cheek;
            }
            if (!_pulling) return;
            var d = (screen - _pullOrigin) * _cheekUnit;
            // 顔の内側へ押し込む向きには変形させない（あごが大きく崩れて見えた。2026-10-17）
            var raw = new Vector2(Mathf.Max(0f, _cheek > 0 ? d.x : -d.x), -d.y) / PullReach;
            var mag = raw.magnitude;
            _pullTarget = mag < 1e-4f ? Vector2.zero : raw * (Tanh(mag) / mag);
            // 上へはほんの少しだけ（引き上げると、あごの輪郭が持ち上がって欠けて見えた。2026-10-17）
            _pullTarget.y = Mathf.Max(_pullTarget.y, PullUpLimit);
            var amount = _pullTarget.magnitude;
            // 速さは、引き始めてからの増え方で見る（引き始めのコマで、それまでの指の動きを速さに数えない）
            if (starting) { _pullAmount = amount; _pullSpeed = 0f; }
            var dt = Mathf.Max(Time.deltaTime, 1e-3f);
            _pullSpeed = Mathf.Lerp(_pullSpeed, Mathf.Max(0f, amount - _pullAmount) / dt, dt * 10f);
            _pullAmount = amount;

            // やさしく引けば困り顔、強く・速く引けば半泣き。強くなったときは、もう一度知らせる
            if (_pullLevel != "hard" && (amount > 0.85f || _pullSpeed > 5f && amount > 0.4f))
            {
                _pullLevel = "hard";
                _pullFace = "teary";
                ForceExpression("teary", 4f);
                Send("pull", "start", 0, _pullLevel, _pullFace);
            }
            else if (_pullLevel == "" && amount > 0.3f)
            {
                _pullLevel = "gentle";
                _pullFace = "troubled";
                ForceExpression("troubled", 3f);
                Send("pull", "start", 0, _pullLevel, _pullFace);
            }
        }

        // Exp を使う式は、遠くまで引くと ∞/∞ = NaN になり、ほっぺと目が戻らなくなった（2026-10-18）
        static float Tanh(float x) => (float)Math.Tanh(x);

        public void Drag(Vector2 screen)
        {
            if (_ignored) return;
            var delta = (screen - _lastPos) / Screen.height;
            _lastPos = screen;
            _travel += delta.magnitude;
            Dragged?.Invoke(screen);
            LookAt(screen);
            if (_cheek != 0) { DragCheek(screen); return; }
            // なぞった髪を指の動きの方向へ押す
            var (part, drawable) = Hit(screen);
            if (part == Part.Hair || drawable != null && drawable.StartsWith("Hair_Front_"))
                PushHair(drawable, delta.x * _hairPush);   // 動かした距離に比例（フレームの速さによらない）
            if (!_stroking && _travel >= _strokeDistance)
            {
                _stroking = true;
                Send("stroke", "start", 0);
                React("stroke");
                StrokeStarted?.Invoke();
            }
            if (_stroking)
            {
                // 撫でる指の左右の動きで、頭が少しついていく
                _strokeAmount = Mathf.MoveTowards(_strokeAmount, 1f, Time.deltaTime * 3f);
                _strokeSway = Mathf.Lerp(_strokeSway, Mathf.Clamp(delta.x * 40f, -1f, 1f), Time.deltaTime * 8f);
            }
        }

        public void Release()
        {
            _pressed = false;
            if (_ignored) return;
            var duration = Time.time - _pressTime;
            var ms = Mathf.RoundToInt(duration * 1000);
            _pokeHeld = false;   // 離すと押す量が 0 へ戻り、物理演算で「ぷるん」と揺れる
            if (_pulling && _pullLevel != "")
            {
                Send("pull", "end", ms, _pullLevel, _pullFace);
                Released?.Invoke("pull");
            }
            else if (_stroking) { Send("stroke", "end", ms); Released?.Invoke("stroke"); }
            else
            {
                var gesture = duration < _tapTime ? "tap" : "hold";
                Send(gesture, "once", gesture == "hold" ? ms : 0);
                React(gesture);
                Released?.Invoke(gesture);
            }
            _stroking = _pulling = false;
            _cheek = 0;
            _pullAmount = _pullSpeed = 0;
        }

        readonly List<RaycastResult> _uiHits = new List<RaycastResult>();

        bool OverUI(Vector2 screen)
        {
            var es = EventSystem.current;
            if (es == null) return false;
            es.RaycastAll(new PointerEventData(es) { position = screen }, _uiHits);
            return _uiHits.Count > 0;
        }

        (Part, string) Hit(Vector2 screen)
        {
            var count = _raycaster.Raycast(_camera.ScreenPointToRay(screen), _hits);
            CubismDrawable front = null;
            var frontZ = float.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                var d = _hits[i].Drawable;
                if (d == null) continue;
                var r = d.GetComponent<CubismRenderer>();
                if (r == null || !r.MeshRenderer.enabled || (float)OpacityProperty.GetValue(r) < 0.1f) continue;
                // メッシュは絵より大きい（透明な余白を含む）ので、絵が描かれている点だけを数える
                if (!Opaque(d, r, _hits[i].WorldPosition)) continue;
                // 奥から手前へ描く並び（BackToFrontZ）。z が小さいほど手前
                var z = r.transform.position.z;
                if (z < frontZ) { frontZ = z; front = d; }
            }
            if (front == null) return (Part.None, null);
            foreach (var (prefix, part) in PartMap)
                if (front.Id.StartsWith(prefix)) return (part, front.Id);
            return (Part.None, front.Id);   // 胸・おなか・首など：反応しない
        }

        // ---- 絵の不透明さ ----
        const int AlphaSize = 1024;      // アトラスを縮小して不透明度だけを持つ
        const float AlphaThreshold = 0.5f;
        readonly Dictionary<Texture, byte[]> _alpha = new Dictionary<Texture, byte[]>();
        readonly Dictionary<CubismDrawable, (Vector2[] uvs, int[] indices)> _meshes = new Dictionary<CubismDrawable, (Vector2[], int[])>();

        bool Opaque(CubismDrawable d, CubismRenderer r, Vector3 world)
        {
            var alpha = AlphaOf(r.MainTexture);
            if (alpha == null) return true;
            if (!_meshes.TryGetValue(d, out var mesh)) _meshes[d] = mesh = (d.VertexUvs, d.Indices);
            var v = d.VertexPositions;
            Vector2 p = d.transform.InverseTransformPoint(world);
            for (int i = 0; i + 2 < mesh.indices.Length; i += 3)
            {
                int a = mesh.indices[i], b = mesh.indices[i + 1], c = mesh.indices[i + 2];
                if (!Barycentric(p, v[a], v[b], v[c], out var w)) continue;
                var uv = mesh.uvs[a] * w.x + mesh.uvs[b] * w.y + mesh.uvs[c] * w.z;
                int x = Mathf.Clamp((int)(uv.x * AlphaSize), 0, AlphaSize - 1), y = Mathf.Clamp((int)(uv.y * AlphaSize), 0, AlphaSize - 1);
                if (alpha[y * AlphaSize + x] >= AlphaThreshold * 255) return true;
            }
            return false;
        }

        static bool Barycentric(Vector2 p, Vector2 a, Vector2 b, Vector2 c, out Vector3 w)
        {
            w = default;
            var den = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
            if (Mathf.Abs(den) < 1e-12f) return false;
            var u = ((b.y - c.y) * (p.x - c.x) + (c.x - b.x) * (p.y - c.y)) / den;
            var t = ((c.y - a.y) * (p.x - c.x) + (a.x - c.x) * (p.y - c.y)) / den;
            w = new Vector3(u, t, 1f - u - t);
            return u >= 0 && t >= 0 && w.z >= 0;
        }

        // アトラスは CPU から読めない設定なので、初回に GPU で縮小コピーして不透明度だけを取り出す
        byte[] AlphaOf(Texture texture)
        {
            if (texture == null) return null;
            if (_alpha.TryGetValue(texture, out var a)) return a;
            var rt = RenderTexture.GetTemporary(AlphaSize, AlphaSize, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.Linear);
            var previous = RenderTexture.active;
            var copy = new Texture2D(AlphaSize, AlphaSize, TextureFormat.RGBA32, false, true);
            try
            {
                Graphics.Blit(texture, rt);
                RenderTexture.active = rt;
                copy.ReadPixels(new Rect(0, 0, AlphaSize, AlphaSize), 0, 0);
                var pixels = copy.GetPixels32();
                a = new byte[pixels.Length];
                for (int i = 0; i < pixels.Length; i++) a[i] = pixels[i].a;
            }
            finally
            {
                RenderTexture.active = previous;
                RenderTexture.ReleaseTemporary(rt);
                Destroy(copy);
            }
            _alpha[texture] = a;
            return a;
        }

        float SideOf(Vector2 screen)
        {
            var center = _face != null ? FaceCenter() : new Vector2(Screen.width / 2f, 0);
            return Mathf.Clamp((screen.x - center.x) / (Screen.height * 0.15f), -1f, 1f);
        }

        void LookAt(Vector2 screen)
        {
            if (_face == null) return;
            var center = FaceCenter();
            var d = (screen - center) / (Screen.height * 0.2f);
            _gazeTarget = Vector2.ClampMagnitude(d, 1f);
        }

        // 顔の中心（画面の座標）。描画の範囲は更新されないことがあるので、今の頂点から求める
        Vector2 FaceCenter() => _camera.WorldToScreenPoint(Center(_face));

        public static Vector3 Center(CubismDrawable d)
        {
            var v = d.VertexPositions;
            var sum = Vector3.zero;
            foreach (var p in v) sum += p;
            return d.transform.TransformPoint(sum / Mathf.Max(v.Length, 1));
        }

        void PushHair(string drawable, float push)
        {
            if (drawable == null) return;
            foreach (var (prefix, output) in HairPhysics)
            {
                if (!drawable.StartsWith(prefix) || !_hairRigs.TryGetValue(output, out var sub)) continue;
                var n = sub.Particles.Length;
                for (int i = 1; i < n; i++)
                    // 先の粒子ほど大きく動く
                    sub.Particles[i].Velocity.x += Mathf.Clamp(push, -3f, 3f) * sub.Particles[i].Radius * 0.25f * i / Mathf.Max(n - 1, 1);
                return;
            }
        }

        // ---- その場の反応 ----

        void React(string gesture)
        {
            var side = Mathf.Sign(_sideX == 0 ? 1 : _sideX);
            switch (_part)
            {
                case Part.Head:
                    if (gesture == "stroke") SetExpression("relaxed", 3f);
                    else { _headDip.Kick(-1f); _earTwitch.Kick(1f); }
                    break;
                case Part.Ear:
                    _earTwitch.Kick(gesture == "tap" ? 1.6f : 0.8f);
                    SetExpression(gesture == "stroke" ? "relaxed" : "surprised", gesture == "stroke" ? 3f : 1.2f);
                    break;
                case Part.Face when _cheek != 0:
                    // ほっぺをつつく：少しだけ逃げて、照れる（押された形・赤みは OnLateUpdate）
                    _headTurn.Kick(-side * 0.4f);
                    SetExpression("embarrassed", 1.5f);
                    break;
                case Part.Face:
                    _headTurn.Kick(-side * 0.8f);   // つつかれた側から少し逃げる
                    SetExpression(gesture == "stroke" ? "embarrassed" : "surprised", gesture == "stroke" ? 3f : 1.2f);
                    break;
                case Part.Hair:
                    if (gesture == "stroke") SetExpression("embarrassed", 2.5f);
                    break;
                case Part.Shoulder:
                    (_drawable.EndsWith("_R") ? _furR : _furL).Kick(1f);   // 触れた側の毛皮
                    _headTurn.Kick(side * 1f);      // 触れられた方を振り向く
                    if (gesture != "stroke") SetExpression("surprised", 1f);
                    break;
                case Part.Hand:
                    SetExpression(gesture == "stroke" ? "embarrassed" : "happy", 2f);
                    break;
            }
        }

        void SetExpression(string name, float ttl)
        {
            // 会話サーバーの表情（話している最中の気持ち）は上書きしない
            if (_expression != null && (_expression.Current == "neutral" || _expression.Current == "thinking"))
                _expression.Set(name, ttl);
        }

        // 痛いときの表情は、会話サーバーの表情より優先する
        void ForceExpression(string name, float ttl)
        {
            if (_expression != null) _expression.Set(name, ttl);
        }

        void Send(string gesture, string phase, int durationMs, string strength = "", string expression = "")
        {
            var part = _cheek != 0 ? "cheek" : PartName(_part);
            LastTouch = $"{part}/{gesture}/{phase}" + (strength != "" ? $"/{strength}/{expression}" : "");
            if (_conversation != null) _conversation.SendTouch(part, gesture, phase, durationMs, strength, expression);
        }

        static string PartName(Part p) => p switch
        {
            Part.Head => "head", Part.Ear => "ear", Part.Face => "face", Part.Hair => "hair",
            Part.Shoulder => "shoulder", Part.Hand => "hand", _ => "none",
        };

        // ---- パラメーターへ反映 ----

        void LateUpdate()
        {
            if (!HasUpdateController) OnLateUpdate();
        }

        public void OnLateUpdate()
        {
            if (!enabled) return;
            var dt = Time.deltaTime;
            if (!_stroking) { _strokeAmount = Mathf.MoveTowards(_strokeAmount, 0f, dt * 1.5f); _strokeSway = Mathf.Lerp(_strokeSway, 0f, dt * 4f); }
            _gazeWeight = Mathf.MoveTowards(_gazeWeight, _pressed && !_ignored ? 1f : 0f, dt * (_pressed ? 6f : 1.5f));
            _gaze = Vector2.Lerp(_gaze, _gazeTarget, dt * 10f);
            foreach (var s in new[] { _earTwitch, _headDip, _headTurn, _furL, _furR }) s.Step(dt);

            var headPat = _part == Part.Head ? _strokeAmount : 0f;
            Add("ParamEyeBallX", _gaze.x * 0.8f * _gazeWeight * (1f - headPat));
            Add("ParamEyeBallY", _gaze.y * 0.8f * _gazeWeight * (1f - headPat));
            // 頭を撫でられる：少しうつむき、指の動きに頭がついていく。耳は寝る
            Add("ParamAngleY", -6f * headPat + 5f * _headDip.X);
            Add("ParamAngleZ", 7f * _strokeSway * headPat);
            Add("ParamAngleX", 10f * _headTurn.X);
            Add("ParamEar", -0.7f * headPat + 0.5f * _earTwitch.X);
            Add("ParamCielFurSwingL", 0.8f * _furL.X);
            Add("ParamCielFurSwingR", 0.8f * _furR.X);
            UpdateCheek(dt);
        }

        void UpdateCheek(float dt)
        {
            // 押す：0.08 秒で押しきり、0.05 秒で離れる（急に戻るので、物理演算の揺れが「ぷるん」と出る）
            _poke = Mathf.MoveTowards(_poke, _pokeHeld ? 1f : 0f, dt * (_pokeHeld ? 12.5f : 20f));
            // 引っ張る：引いているあいだは指に素早くついていき、離すと、ばねで少し行き過ぎながら戻る
            if (_pulling) { _pull = Vector2.Lerp(_pull, _pullTarget, Mathf.Min(1f, dt * 25f)); _pullVel = Vector2.zero; }
            else
            {
                var step = Mathf.Min(dt, 1f / 30f) / 4f;
                for (int i = 0; i < 4; i++)
                {
                    _pullVel += (-380f * _pull - 11f * _pullVel) * step;
                    _pull += _pullVel * step;
                }
            }
            // 万一、値が壊れても（NaN・∞）、元の形へ戻す
            if (!float.IsFinite(_pull.x) || !float.IsFinite(_pull.y) || !float.IsFinite(_pullVel.x) || !float.IsFinite(_pullVel.y))
                _pull = _pullTarget = _pullVel = Vector2.zero;
            var pull = _pull.magnitude;
            // 赤み：押す・引くと早く上がり、ゆっくり引く
            var blush = Mathf.Max(_pokeHeld ? 0.35f : 0f, _pulling ? 0.35f + 0.4f * pull : 0f);
            _blush = Mathf.MoveTowards(_blush, blush, dt * (blush > _blush ? 4f : 0.5f));

            var poke = _pokeSide > 0 ? "L" : "R";
            var pulled = _pullSide > 0 ? "L" : "R";
            Add("ParamCielCheekPoke" + poke, _poke);
            Add("ParamCielCheekPullX" + pulled, Mathf.Max(_pull.x, -0.1f));   // 戻るときの行き過ぎも、内側へは小さく
            Add("ParamCielCheekPullY" + pulled, Mathf.Max(_pull.y, PullUpLimit));
            Add("ParamCheek", _blush);
            // 押された・引かれた側の目を少し細める（笑い目の途中の値は二重に見えたので、開き具合で）
            Add(_pokeSide > 0 ? "ParamEyeLOpen" : "ParamEyeROpen", -0.22f * _poke);
            Add(_pullSide > 0 ? "ParamEyeLOpen" : "ParamEyeROpen", -0.25f * Mathf.Min(pull, 1f));
        }

        void Add(string id, float v)
        {
            if (Mathf.Abs(v) < 1e-4f || !_params.TryGetValue(id, out var p)) return;
            p.Value = Mathf.Clamp(p.Value + v, p.MinimumValue, p.MaximumValue);
        }

        // 揺れて止まるばね（Kick で揺らし始める）
        sealed class Spring
        {
            public float X, V;
            const float Stiffness = 120f, Damping = 9f;
            public void Kick(float v) => V += v * 10f;
            public void Step(float dt)
            {
                dt = Mathf.Min(dt, 1f / 30f);
                V += (-Stiffness * X - Damping * V) * dt;
                X += V * dt;
            }
        }
    }
}
