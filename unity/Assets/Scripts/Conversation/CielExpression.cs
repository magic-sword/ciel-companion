// シエルの表情を切り替える。会話サーバーの表情のイベント（character.expression）か、画面の確認用のボタンから使う。
//
// 表情は Live2D の表情ファイル（*.exp3.json、Cubism の表情の仕組み）に置き換える予定。それまでの仮として、
// 表情ごとに「パラメーターの目標値」を下の表に持ち、なめらかに近づける（加算。目パチ・口パク・頭の動きと重ねられる）。
// リグに各パラメーターの形（笑い目・眉・口の形・頬など）が入ると、見た目が変わる。
// 寿命（ttl）が切れたら、通常（neutral）へ戻る。
using System.Collections.Generic;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace Ciel.Conversation
{
    // シエルのモデル（CubismModel と同じ GameObject）に付ける。Cubism の更新の順番で、ほかの制御（目パチ・口パク・揺れ）の後に動く
    public sealed class CielExpression : MonoBehaviour, ICubismUpdatable
    {
        [SerializeField] CubismModel _model;
        [Tooltip("表情が切り替わる速さ（秒）")]
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

        // 表情 → パラメーターの加算量（仮。表情ファイルを作るまで）
        static readonly Dictionary<string, (string id, float v)[]> Targets = new Dictionary<string, (string, float)[]>
        {
            { "neutral", new (string, float)[0] },
            { "happy", new[] { ("ParamEyeLSmile", 1f), ("ParamEyeRSmile", 1f), ("ParamMouthForm", 1f), ("ParamBrowLY", 0.3f), ("ParamBrowRY", 0.3f), ("ParamEar", 1f) } },
            { "relaxed", new[] { ("ParamEyeLSmile", 0.6f), ("ParamEyeRSmile", 0.6f), ("ParamMouthForm", 0.6f) } },
            { "surprised", new[] { ("ParamEyeLOpen", 0.3f), ("ParamEyeROpen", 0.3f), ("ParamBrowLY", 0.8f), ("ParamBrowRY", 0.8f), ("ParamEar", 1f) } },
            { "angry", new[] { ("ParamBrowLAngle", -0.8f), ("ParamBrowRAngle", -0.8f), ("ParamBrowLForm", -0.6f), ("ParamBrowRForm", -0.6f), ("ParamMouthForm", -0.6f), ("ParamCheek", 0.3f), ("ParamEar", -0.5f) } },
            { "sad", new[] { ("ParamBrowLAngle", 0.7f), ("ParamBrowRAngle", 0.7f), ("ParamBrowLY", -0.3f), ("ParamBrowRY", -0.3f), ("ParamMouthForm", -0.7f), ("ParamEyeLOpen", -0.2f), ("ParamEyeROpen", -0.2f), ("ParamEar", -1f) } },
            { "troubled", new[] { ("ParamBrowLAngle", 0.9f), ("ParamBrowRAngle", 0.9f), ("ParamMouthForm", -0.2f), ("ParamEar", -0.4f) } },
            { "embarrassed", new[] { ("ParamCheek", 1f), ("ParamEyeLSmile", 0.3f), ("ParamEyeRSmile", 0.3f), ("ParamEyeBallX", 0.6f), ("ParamEar", -0.3f) } },
            { "teary", new[] { ("ParamBrowLAngle", 0.9f), ("ParamBrowRAngle", 0.9f), ("ParamMouthForm", -0.8f), ("ParamEyeLOpen", -0.15f), ("ParamEyeROpen", -0.15f), ("ParamEar", -1f) } },
            { "excited", new[] { ("ParamEyeLOpen", 0.2f), ("ParamEyeROpen", 0.2f), ("ParamMouthForm", 1f), ("ParamBrowLY", 0.6f), ("ParamBrowRY", 0.6f), ("ParamEar", 1f) } },
            { "jitome", new[] { ("ParamEyeLOpen", -0.5f), ("ParamEyeROpen", -0.5f), ("ParamMouthForm", -0.3f), ("ParamEar", -0.5f) } },
            { "thinking", new[] { ("ParamEyeBallX", -0.5f), ("ParamEyeBallY", 0.6f), ("ParamBrowLY", 0.4f), ("ParamMouthForm", -0.3f) } },
        };

        public string Current { get; private set; } = "neutral";
        float _until = float.PositiveInfinity;
        readonly Dictionary<string, CubismParameter> _params = new Dictionary<string, CubismParameter>();
        readonly Dictionary<string, float> _weights = new Dictionary<string, float>();   // パラメーター → 今の加算量

        public int ExecutionOrder => 10000;
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }

        void Start() => HasUpdateController = GetComponent<CubismUpdateController>() != null;

        void Awake()
        {
            if (_model == null) _model = GetComponent<CubismModel>();
            foreach (var p in _model.Parameters) _params[p.Id] = p;
        }

        /// 表情を切り替える。ttlSeconds が過ぎたら通常へ戻る（0 以下なら戻らない）
        public void Set(string name, float ttlSeconds = 0f)
        {
            if (!Targets.ContainsKey(name)) { Debug.LogWarning($"[CielExpression] 知らない表情: {name}"); return; }
            Current = name;
            _until = ttlSeconds > 0 ? Time.time + ttlSeconds : float.PositiveInfinity;
        }

        void LateUpdate()
        {
            if (!HasUpdateController) OnLateUpdate();
        }

        // 目パチ・口パク・頭の動きなど、ほかの制御の後に足す
        public void OnLateUpdate()
        {
            if (!enabled) return;
            if (Current != "neutral" && Time.time > _until) Current = "neutral";
            var target = new Dictionary<string, float>();
            foreach (var (id, v) in Targets[Current]) target[id] = v;
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
                    p.Value = Mathf.Clamp(p.Value + w * (p.MaximumValue - p.MinimumValue) * 0.5f, p.MinimumValue, p.MaximumValue);
            }
        }
    }
}
