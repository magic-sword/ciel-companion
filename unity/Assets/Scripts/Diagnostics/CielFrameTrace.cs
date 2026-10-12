// 確認用：1 秒ごとにフレーム数をログに出す（再生が止まっていないかを見る）。
using UnityEngine;

namespace Ciel.Diagnostics
{
    public sealed class CielFrameTrace : MonoBehaviour
    {
        float _next;
        void Update()
        {
            if (Time.realtimeSinceStartup < _next) return;
            _next = Time.realtimeSinceStartup + 1f;
            Debug.Log($"[CielFrameTrace] frame={Time.frameCount} t={Time.realtimeSinceStartup:0.0}");
        }
    }
}
