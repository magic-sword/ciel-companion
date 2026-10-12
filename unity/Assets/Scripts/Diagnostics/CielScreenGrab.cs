// 確認用：再生中の画面（Game ビュー）を数回撮って保存する。エディタの確認の道具（CielPlayModeShot）が付ける。
using System.Collections;
using System.IO;
using UnityEngine;

namespace Ciel.Diagnostics
{
    public sealed class CielScreenGrab : MonoBehaviour
    {
        public string OutDir;
        public float[] Times = { 1.5f, 3f, 6f };

        IEnumerator Start()
        {
            for (int i = 0; i < Times.Length; i++)
            {
                while (Time.realtimeSinceStartup < Times[i] + _start) yield return null;
                yield return new WaitForEndOfFrame();
                var tex = ScreenCapture.CaptureScreenshotAsTexture();
                File.WriteAllBytes(Path.Combine(OutDir, $"screen-{i}.png"), tex.EncodeToPNG());
                Destroy(tex);
            }
            Done = true;
        }

        float _start;
        void Awake() => _start = Time.realtimeSinceStartup;
        public bool Done { get; private set; }
    }
}
