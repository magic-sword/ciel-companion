// シエルの体の短い動き（アプリの道具 app_gesture。CielConversation.App.cs）。
// うなずく（nod）・首をかしげる（tilt）・首を横にふる（shake）・耳をぴくっと動かす（ear）。
// タッチの反応（CielTouch）と同じく、頭の角度と耳のパラメーターに、その場で値を足す（表情・目線・物理演算はそのまま）。
// 頭の角度は物理演算の入力なので、髪も一緒に揺れる。腕を振る動きはリグが無いので出さない。
// 動きの大きさ・長さは目で見て直すこと（docs/app/live2d/ciel-live2d-rig-design-ja.md。合否は自然でかわいいか）。
using System.Collections.Generic;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace Ciel.Conversation
{
    // シエルのモデル（CubismModel と同じ GameObject）に付ける。CielConversation が要るときに付ける
    public sealed class CielGesture : MonoBehaviour, ICubismUpdatable
    {
        readonly Dictionary<string, CubismParameter> _params = new Dictionary<string, CubismParameter>();
        string _now = "";
        float _start, _length;

        public int ExecutionOrder => 760;   // タッチの反応（750）の後、物理演算（800）の前
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }

        static readonly Dictionary<string, float> Lengths = new Dictionary<string, float>
        {
            { "nod", 0.9f }, { "tilt", 1.8f }, { "shake", 1.1f }, { "ear", 0.6f },
        };

        void Awake()
        {
            var model = GetComponent<CubismModel>();
            if (model != null) foreach (var p in model.Parameters) _params[p.Id] = p;
        }

        /// 動きを始める（知らない動きなら false）。動いている途中なら、新しい動きに替える
        public bool Play(string gesture)
        {
            if (gesture == null || !Lengths.TryGetValue(gesture, out var length)) return false;
            (_now, _start, _length) = (gesture, Time.time, length);
            return true;
        }

        void LateUpdate()
        {
            if (!HasUpdateController) OnLateUpdate();
        }

        public void OnLateUpdate()
        {
            if (!enabled || _now == "") return;
            var t = Time.time - _start;
            if (t >= _length) { _now = ""; return; }
            var u = t / _length;   // 0〜1
            switch (_now)
            {
                case "nod":
                    // 2 回うなずく（2 回目は小さく）
                    var dip = u < 0.55f ? Mathf.Sin(Mathf.PI * u / 0.55f) : 0.45f * Mathf.Sin(Mathf.PI * (u - 0.55f) / 0.45f);
                    Add("ParamAngleY", -12f * dip);
                    break;
                case "tilt":
                    // 傾けて少し止まり、戻す
                    var tilt = Smooth(Mathf.Clamp01(u / 0.25f)) * (1f - Smooth(Mathf.Clamp01((u - 0.7f) / 0.3f)));
                    Add("ParamAngleZ", 12f * tilt);
                    Add("ParamAngleX", 4f * tilt);
                    break;
                case "shake":
                    // 左右に 2 往復、だんだん小さく
                    Add("ParamAngleX", 14f * Mathf.Sin(Mathf.PI * 4f * u) * (1f - u));
                    break;
                case "ear":
                    Add("ParamEar", 0.6f * Mathf.Sin(Mathf.PI * 4f * u) * (1f - u));
                    break;
            }
        }

        static float Smooth(float x) => x * x * (3f - 2f * x);

        void Add(string id, float v)
        {
            if (Mathf.Abs(v) < 1e-4f || !_params.TryGetValue(id, out var p)) return;
            p.Value = Mathf.Clamp(p.Value + v, p.MinimumValue, p.MaximumValue);
        }
    }
}
