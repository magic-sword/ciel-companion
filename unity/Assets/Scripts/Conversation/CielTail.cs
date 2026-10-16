using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace Ciel.Conversation
{
    // Intentional wag input runs before Cubism physics. Follow-through is
    // evaluated by the model's physics rig, with one state for both tail views.
    public sealed class CielTail : MonoBehaviour, ICubismUpdatable
    {
        [SerializeField, Min(0.1f)] float _cyclesPerSecond = 1.2f;
        [SerializeField, Min(0.1f)] float _amplitudeResponse = 2.5f;

        CubismParameter _wag;
        CielExpression _expression;
        float _phase;
        float _amplitude;
        float _manualStrength;
        float _manualUntil = float.NegativeInfinity;
        float _manualFrequency;

        public int ExecutionOrder => 760;
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }

        void Awake()
        {
            var model = GetComponent<CubismModel>();
            if (model != null)
                _wag = System.Array.Find(model.Parameters, p => p.Id == "ParamCielTailWag");
            _expression = GetComponent<CielExpression>();
        }

        void Start() => HasUpdateController = GetComponent<CubismUpdateController>() != null;

        [ContextMenu("Wag tail (Play mode)")]
        void PreviewWag()
        {
            if (Application.isPlaying) Wag();
        }

        /// <summary>Wag for a limited time; strength is 0..1, frequency is cycles per second.</summary>
        public void Wag(float strength = 1f, float seconds = 2f, float cyclesPerSecond = 1.2f)
        {
            if (float.IsNaN(strength) || float.IsNaN(seconds) || float.IsNaN(cyclesPerSecond)
                || float.IsInfinity(strength) || float.IsInfinity(seconds) || float.IsInfinity(cyclesPerSecond)) return;
            _manualStrength = Mathf.Clamp01(strength);
            _manualFrequency = Mathf.Clamp(cyclesPerSecond, 0.1f, 3f);
            _manualUntil = Time.time + Mathf.Clamp(seconds, 0f, 60f);
        }

        void LateUpdate()
        {
            if (!HasUpdateController) OnLateUpdate();
        }

        public void OnLateUpdate()
        {
            if (!enabled || _wag == null) return;
            var manual = Time.time < _manualUntil;
            float target = manual ? _manualStrength : ExpressionStrength();
            _amplitude = Mathf.MoveTowards(_amplitude, target, _amplitudeResponse * Time.deltaTime);
            float frequency = manual ? _manualFrequency : _cyclesPerSecond;
            // Never restart the phase when switching materials or expressions.
            _phase = Mathf.Repeat(_phase + 2f * Mathf.PI * frequency * Time.deltaTime, 2f * Mathf.PI);
            _wag.Value = Mathf.Clamp(_amplitude * Mathf.Sin(_phase), _wag.MinimumValue, _wag.MaximumValue);
        }

        float ExpressionStrength()
        {
            if (_expression == null) _expression = GetComponent<CielExpression>();
            switch (_expression != null ? _expression.Current : "neutral")
            {
                case "happy": return 0.9f;
                case "excited": return 1f;
                default: return 0f;
            }
        }
    }
}
