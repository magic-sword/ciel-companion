// シエルの表情を切り替える。会話サーバーの表情のイベント（character.expression）か、画面の確認用のボタンから使う。
//
// 表情は Live2D の表情ファイル（*.exp3.json、Cubism の表情の仕組み）に置き換える予定。それまでの仮として、
// 表情ごとに「パラメーターの目標値」を持ち、なめらかに近づける。専用の顔切り替えは上書き、動作と重ねる値は加算。
// リグの笑い目・頬・涙・汗・キラキラと、眉・口・耳の変形を制御する。
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
            { "happy", new[] { ("ParamEyeLSmile", 1f), ("ParamEyeRSmile", 1f), ("ParamCheek", 0.45f), ("ParamMouthOpenY", 0.8f), ("ParamMouthForm", 1f), ("ParamBrowLY", 0.3f), ("ParamBrowRY", 0.3f), ("ParamEar", 1f) } },
            { "relaxed", new[] { ("ParamEyeLOpen", -0.25f), ("ParamEyeROpen", -0.25f), ("ParamMouthForm", 0.6f), ("ParamCheek", 0.2f) } },
            { "surprised", new[] { ("ParamEyeLOpen", 0.3f), ("ParamEyeROpen", 0.3f), ("ParamMouthOpenY", 0.3f), ("ParamBrowLY", 0.8f), ("ParamBrowRY", 0.8f), ("ParamEar", 1f) } },
            { "angry", new[] { ("ParamBrowLAngle", -0.8f), ("ParamBrowRAngle", -0.8f), ("ParamBrowLForm", -0.6f), ("ParamBrowRForm", -0.6f), ("ParamMouthForm", -0.6f), ("ParamCheek", 0.3f), ("ParamEar", -0.5f) } },
            { "sad", new[] { ("ParamBrowLAngle", 0.7f), ("ParamBrowRAngle", 0.7f), ("ParamBrowLY", -0.3f), ("ParamBrowRY", -0.3f), ("ParamMouthForm", -0.7f), ("ParamEyeLOpen", -0.2f), ("ParamEyeROpen", -0.2f), ("ParamEar", -1f) } },
            { "troubled", new[] { ("ParamBrowLAngle", 0.9f), ("ParamBrowRAngle", 0.9f), ("ParamMouthForm", -0.2f), ("ParamSweat", 1f), ("ParamEar", -0.4f) } },
            { "embarrassed", new[] { ("ParamCheek", 1f), ("ParamMouthForm", 0.2f), ("ParamEyeBallX", 0.6f), ("ParamEar", -0.3f) } },
            { "teary", new[] { ("ParamBrowLAngle", 0.9f), ("ParamBrowRAngle", 0.9f), ("ParamMouthForm", -0.8f), ("ParamEyeLOpen", -0.15f), ("ParamEyeROpen", -0.15f), ("ParamTear", 1f), ("ParamEar", -1f) } },
            { "excited", new[] { ("ParamEyeLOpen", 0.2f), ("ParamEyeROpen", 0.2f), ("ParamSparkle", 1f), ("ParamMouthOpenY", 0.9f), ("ParamMouthForm", 1f), ("ParamBrowLY", 0.6f), ("ParamBrowRY", 0.6f), ("ParamEar", 1f) } },
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

        Dictionary<string, float> GetTargets()
        {
            var target = new Dictionary<string, float>();
            // 専用キーがある表情は旧来の目・口・耳の値を重ねない。
            if (Current == "embarrassed" && _params.ContainsKey("ParamEmbarrassed"))
            {
                target["ParamCheek"] = 0f;
            }
            else if ((Current == "angry" && _params.ContainsKey("ParamAngry")) ||
                (Current == "sad" && _params.ContainsKey("ParamSad")) ||
                (Current == "troubled" && _params.ContainsKey("ParamTroubled")))
            {
                target["ParamCheek"] = 0.2f;
            }
            else if (Current == "surprised" && _params.ContainsKey("ParamSurprised"))
            {
                target["ParamEar"] = 1f;
                target["ParamBrowLY"] = target["ParamBrowRY"] = 0.8f;
                target["ParamCheek"] = 0.15f;
            }
            else if (Current != "relaxed" || !_params.ContainsKey("ParamRelaxed"))
                foreach (var (id, v) in Targets[Current]) target[id] = v;
            if (_params.ContainsKey("ParamHappy")) target["ParamHappy"] = Current == "happy" ? 1f : 0f;
            if (_params.ContainsKey("ParamRelaxed")) target["ParamRelaxed"] = Current == "relaxed" ? 1f : 0f;
            if (_params.ContainsKey("ParamSurprised")) target["ParamSurprised"] = Current == "surprised" ? 1f : 0f;
            if (_params.ContainsKey("ParamAngry")) target["ParamAngry"] = Current == "angry" ? 1f : 0f;
            if (_params.ContainsKey("ParamSad")) target["ParamSad"] = Current == "sad" ? 1f : 0f;
            if (_params.ContainsKey("ParamTroubled")) target["ParamTroubled"] = Current == "troubled" ? 1f : 0f;
            if (_params.ContainsKey("ParamEmbarrassed")) target["ParamEmbarrassed"] = Current == "embarrassed" ? 1f : 0f;
            if (_params.ContainsKey("ParamEarFold"))
                target["ParamEarFold"] = (Current == "angry" && _params.ContainsKey("ParamAngry")) ||
                    (Current == "sad" && _params.ContainsKey("ParamSad")) ||
                    (Current == "troubled" && _params.ContainsKey("ParamTroubled")) ||
                    (Current == "embarrassed" && _params.ContainsKey("ParamEmbarrassed")) ? 1f : 0f;
            return target;
        }

        // 目パチ・口パク・頭の動きなど、ほかの制御の後に適用する
        public void OnLateUpdate()
        {
            if (!enabled) return;
            if (Current != "neutral" && Time.time > _until) Current = "neutral";
            var target = GetTargets();
            var keys = new HashSet<string>(_weights.Keys);
            keys.UnionWith(target.Keys);
            var step = Time.deltaTime / Mathf.Max(_fadeTime, 1e-3f);
            foreach (var id in keys)
            {
                _weights.TryGetValue(id, out var w);
                target.TryGetValue(id, out var t);
                w = Mathf.MoveTowards(w, t, step);
                _weights[id] = w;
                if (!_params.TryGetValue(id, out var p)) continue;
                if (id == "ParamHappy" || id == "ParamRelaxed" || id == "ParamSurprised" ||
                    id == "ParamAngry" || id == "ParamSad" || id == "ParamTroubled" || id == "ParamEmbarrassed" || id == "ParamEarFold")
                    // 専用の切り替え値は毎フレーム上書きし、通常復帰時も0へ戻す。
                    p.Value = Mathf.Clamp(w, p.MinimumValue, p.MaximumValue);
                else if (Mathf.Abs(w) > 1e-4f)
                    // 値はパラメーターの単位。0〜1 の素材表示にも 1 をそのまま渡す。
                    p.Value = Mathf.Clamp(p.Value + w, p.MinimumValue, p.MaximumValue);
            }
        }
    }
}
