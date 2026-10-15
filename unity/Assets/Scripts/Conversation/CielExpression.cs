// シエルの表情を切り替える。会話サーバーの表情のイベント（character.expression）か、画面の確認用のボタンから使う。
//
// 表情の中身は Cubism で作った表情ファイル（Expressions/*.exp3.json）。モデルの CubismExpressionController に
// 表情の番号を渡し、フェードと値の適用は Cubism に任せる。表情はまばたき・口パクより前に適用されるので、
// 話している間も口は動き、専用の口の素材への切り替えはリグが行う。
// 表情ファイルの無い「考え中（thinking）」は、通常の顔に目線だけを重ねる。
// 寿命（ttl）が切れたら、通常（neutral）へ戻る。
using System.Collections.Generic;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using Live2D.Cubism.Framework.Expression;
using UnityEngine;

namespace Ciel.Conversation
{
    // シエルのモデル（CubismModel・CubismExpressionController と同じ GameObject）に付ける
    public sealed class CielExpression : MonoBehaviour, ICubismUpdatable
    {
        [SerializeField] CubismModel _model;
        [SerializeField] CubismExpressionController _controller;
        [Tooltip("考え中の目線が動く速さ（秒）")]
        [SerializeField] float _fadeTime = 0.25f;

        public static readonly string[] Names =
        {
            "neutral", "happy", "relaxed", "surprised", "angry", "sad",
            "troubled", "embarrassed", "teary", "excited", "jitome", "thinking",
        };

        public static readonly Dictionary<string, string> JapaneseNames = new Dictionary<string, string>
        {
            { "neutral", "通常" }, { "happy", "嬉しい" }, { "relaxed", "にこにこ" }, { "surprised", "驚き" },
            { "angry", "ぷんすか" }, { "sad", "しょんぼり" }, { "troubled", "困り" }, { "embarrassed", "照れ" },
            { "teary", "半泣き" }, { "excited", "わくわく" }, { "jitome", "ジト目" }, { "thinking", "考え中" },
        };

        // 表情ファイルの無い表情：使う表情ファイルと、その上に重ねる値（パラメーターの単位で加算）
        static readonly Dictionary<string, (string baseName, (string id, float v)[] add)> Composed =
            new Dictionary<string, (string, (string, float)[])>
        {
            { "thinking", ("neutral", new[] { ("ParamEyeBallX", -0.5f), ("ParamEyeBallY", 0.6f) }) },
        };

        public string Current { get; private set; } = "neutral";
        float _until = float.PositiveInfinity;
        readonly Dictionary<string, int> _indices = new Dictionary<string, int>();
        readonly Dictionary<string, CubismParameter> _params = new Dictionary<string, CubismParameter>();
        readonly Dictionary<string, float> _weights = new Dictionary<string, float>();   // 重ねる値 → 今の加算量

        // 目線（CubismLookController）の後、描画の前
        public int ExecutionOrder => 900;
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }

        void Awake()
        {
            if (_model == null) _model = GetComponent<CubismModel>();
            if (_controller == null) _controller = GetComponent<CubismExpressionController>();
            foreach (var p in _model.Parameters) _params[p.Id] = p;
            var list = _controller != null ? _controller.ExpressionsList : null;
            if (list == null || list.CubismExpressionObjects == null)
            {
                Debug.LogError("[CielExpression] モデルに表情ファイルの一覧（CubismExpressionController）が無い");
                return;
            }
            for (int i = 0; i < list.CubismExpressionObjects.Length; i++)
            {
                var data = list.CubismExpressionObjects[i];
                if (data != null) _indices[data.name.Replace(".exp3", "")] = i;
            }
            foreach (var n in Names)
                if (!Has(n)) Debug.LogWarning($"[CielExpression] 表情ファイルが無い: {n}");
        }

        void Start()
        {
            HasUpdateController = GetComponent<CubismUpdateController>() != null;
            Apply();
        }

        /// 表情ファイル（または組み合わせ）がある表情か
        public bool Has(string name) =>
            _indices.ContainsKey(name) || (Composed.TryGetValue(name, out var c) && _indices.ContainsKey(c.baseName));

        /// 表情を切り替える。ttlSeconds が過ぎたら通常へ戻る（0 以下なら戻らない）
        public void Set(string name, float ttlSeconds = 0f)
        {
            if (string.IsNullOrEmpty(name) || !Has(name)) { Debug.LogWarning($"[CielExpression] 知らない表情: {name}"); return; }
            Current = name;
            _until = ttlSeconds > 0 ? Time.time + ttlSeconds : float.PositiveInfinity;
            Apply();
        }

        // 表情ファイルの番号を Cubism へ渡す。同じ番号なら Cubism は何もしない
        void Apply()
        {
            if (_controller == null) return;
            var file = Composed.TryGetValue(Current, out var c) ? c.baseName : Current;
            if (_indices.TryGetValue(file, out var index)) _controller.CurrentExpressionIndex = index;
        }

        void LateUpdate()
        {
            if (!HasUpdateController) OnLateUpdate();
        }

        public void OnLateUpdate()
        {
            if (!enabled) return;
            if (Current != "neutral" && Time.time > _until) Set("neutral");
            // 組み合わせの表情の重ねる値を、なめらかに出し入れする
            var target = new Dictionary<string, float>();
            if (Composed.TryGetValue(Current, out var c))
                foreach (var (id, v) in c.add) target[id] = v;
            var keys = new HashSet<string>(_weights.Keys);
            keys.UnionWith(target.Keys);
            var step = Time.deltaTime / Mathf.Max(_fadeTime, 1e-3f);
            foreach (var id in keys)
            {
                _weights.TryGetValue(id, out var w);
                target.TryGetValue(id, out var t);
                w = Mathf.MoveTowards(w, t, step);
                _weights[id] = w;
                if (Mathf.Abs(w) > 1e-4f && _params.TryGetValue(id, out var p))
                    p.Value = Mathf.Clamp(p.Value + w, p.MinimumValue, p.MaximumValue);
            }
        }
    }
}
