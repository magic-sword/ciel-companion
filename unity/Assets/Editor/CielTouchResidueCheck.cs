// 会話シーンを再生し、ほっぺ・顔・頭などに何度も触れたあと、しばらく待って体が元の形へ戻るかを確かめる。
// （触れ合ったあと右目が細いまま戻らない、という報告の再現用。2026-10-18）
// Unity.exe -projectPath unity -executeMethod Ciel.EditorTools.CielTouchResidueCheck.Run -logFile <log>
// 出力：.local/touch-residue/before.png・after.png と report.txt
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Ciel.Conversation;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielTouchResidueCheck
    {
        const string ActiveKey = "Ciel.TouchResidue.Active";
        const string ExitKey = "Ciel.TouchResidue.Exit";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/touch-residue"));

        static CielTouch _touch;
        static CubismModel _model;
        static Camera _camera;
        static float _start;
        static Dictionary<string, float> _before;
        static StringBuilder _report;
        static int _phase;
        static float _phaseStart;
        static readonly List<(float t, Action a)> _script = new List<(float, Action)>();
        static int _next;

        public static void Run()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
            foreach (var c in UnityEngine.Object.FindObjectsByType<CielConversation>())
            {
                var so = new SerializedObject(c);
                so.FindProperty("_connectOnStart").boolValue = false;
                so.ApplyModifiedPropertiesWithoutUndo();
            }
            SessionState.SetBool(ActiveKey, true);
            EditorApplication.EnterPlaymode();
        }

        [InitializeOnLoadMethod]
        static void Register()
        {
            EditorApplication.playModeStateChanged += state =>
            {
                if (!SessionState.GetBool(ActiveKey, false)) return;
                if (state == PlayModeStateChange.EnteredPlayMode) Begin();
                if (state == PlayModeStateChange.EnteredEditMode)
                {
                    SessionState.SetBool(ActiveKey, false);
                    EditorApplication.Exit(SessionState.GetInt(ExitKey, 1));
                }
            };
        }

        static void Begin()
        {
            Directory.CreateDirectory(OutDir);
            _touch = UnityEngine.Object.FindAnyObjectByType<CielTouch>();
            _model = _touch.GetComponent<CubismModel>();
            _camera = Camera.main;
            _report = new StringBuilder();
            _phase = 0;
            _phaseStart = Time.time + 2f;   // 物理演算が落ち着くのを待つ
            EditorApplication.update += Tick;
        }

        static Dictionary<string, float> Snapshot() => _model.Parameters.ToDictionary(p => p.Id, p => p.Value);

        static Vector2 CheekPoint(int side)
        {
            var d = _model.Drawables.First(x => x.Id == (side > 0 ? "Cheek_Dimple_L" : "Cheek_Dimple_R"));
            Vector2 p = _camera.WorldToScreenPoint(CielTouch.Center(d));
            for (int i = 0; i < 40; i++)
            {
                var q = p + new Vector2(0, i * 2f);
                if (_touch.CheekAt(q) == side) return q;
            }
            throw new InvalidOperationException("cheek point not found");
        }

        static void BuildScript()
        {
            _script.Clear();
            var r = CheekPoint(-1);
            var l = CheekPoint(1);
            _report.AppendLine($"screen={Screen.width}x{Screen.height} cheekL={l} cheekR={r}");
            var t = 0f;
            void At(float dt, Action a) { t += dt; _script.Add((t, a)); }
            // 右のほっぺを何度もつつく
            for (int i = 0; i < 6; i++) { At(0.05f, () => _touch.Press(r)); At(0.08f, () => _touch.Release()); }
            // 右のほっぺを引っ張る（いろいろな向き）
            foreach (var dir in new[] { new Vector2(-60, -40), new Vector2(-120, 0), new Vector2(0, -150), new Vector2(40, 60), new Vector2(-30, 80) })
            {
                At(0.3f, () => _touch.Press(r));
                for (int k = 1; k <= 10; k++) { var kk = k; At(0.02f, () => _touch.Drag(r + dir * kk / 10f)); }
                At(0.2f, () => _touch.Release());
            }
            // 引っ張りが戻りきらないうちに、反対のほっぺ・右のほっぺを交互に
            for (int i = 0; i < 4; i++)
            {
                At(0.05f, () => _touch.Press(r));
                for (int k = 1; k <= 5; k++) { var kk = k; At(0.02f, () => _touch.Drag(r + new Vector2(-100, -50) * kk / 5f)); }
                At(0.02f, () => _touch.Release());
                At(0.05f, () => _touch.Press(l));
                At(0.05f, () => _touch.Release());
            }
            // 左のほっぺをつまんで、画面の外まで遠く引っ張る
            At(0.3f, () => _touch.Press(l));
            for (int k = 1; k <= 20; k++) { var kk = k; At(0.02f, () => _touch.Drag(l + new Vector2(Screen.width * 3f, -Screen.height * 2f) * kk / 20f)); }
            At(0.2f, () => _touch.Release());
        }

        static void Tick()
        {
            if (!EditorApplication.isPlaying) return;
            try
            {
                var t = Time.time - _phaseStart;
                if (t < 0) return;
                switch (_phase)
                {
                    case 0:
                        _before = Snapshot();
                        Shot("before");
                        BuildScript();
                        _next = 0;
                        _phase = 1; _phaseStart = Time.time;
                        return;
                    case 1:
                        while (_next < _script.Count && _script[_next].t <= t) { _script[_next].a(); _next++; }
                        if (_next >= _script.Count) { _phase = 2; _phaseStart = Time.time + 4f; }
                        return;
                    case 2:
                        var after = Snapshot();
                        Shot("after");
                        var bad = 0;
                        // 頭・体・呼吸・髪はふだんから揺れているので、タッチで動かす部分だけを比べる
                        foreach (var kv in after.Where(k => k.Key.Contains("Eye") || k.Key.Contains("Cheek") || k.Key.StartsWith("ParamEar") || k.Key.Contains("Fur")).OrderBy(k => k.Key))
                        {
                            var d = kv.Value - _before[kv.Key];
                            if (Mathf.Abs(d) > 0.02f) { bad++; _report.AppendLine($"{kv.Key}: before={_before[kv.Key]:0.000} after={kv.Value:0.000}"); }
                        }
                        _report.AppendLine(bad == 0 ? "OK: all parameters returned" : $"NG: {bad} parameters did not return");
                        File.WriteAllText(Path.Combine(OutDir, "report.txt"), _report.ToString());
                        Debug.Log("[CielTouchResidueCheck]\n" + _report);
                        SessionState.SetInt(ExitKey, bad == 0 ? 0 : 2);
                        EditorApplication.update -= Tick;
                        EditorApplication.ExitPlaymode();
                        return;
                }
            }
            catch (Exception e)
            {
                Debug.LogError("[CielTouchResidueCheck] " + e);
                File.WriteAllText(Path.Combine(OutDir, "report.txt"), e.ToString());
                SessionState.SetInt(ExitKey, 1);
                EditorApplication.update -= Tick;
                EditorApplication.ExitPlaymode();
            }
        }

        static void Shot(string name)
        {
            var rt = new RenderTexture(Screen.width, Screen.height, 24);
            var prev = _camera.targetTexture;
            _camera.targetTexture = rt;
            _camera.Render();
            _camera.targetTexture = prev;
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            RenderTexture.active = null;
            File.WriteAllBytes(Path.Combine(OutDir, name + ".png"), tex.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(tex);
            rt.Release();
        }
    }
}
