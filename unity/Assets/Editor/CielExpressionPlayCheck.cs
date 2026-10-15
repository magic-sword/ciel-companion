// 実際の再生ループで表情・フェード・TTLを確認し、確認画像を保存する。
// Unity.exe -batchmode -projectPath unity -executeMethod Ciel.EditorTools.CielExpressionPlayCheck.Run -logFile <log>
using System;
using System.IO;
using System.Text;
using Ciel.Conversation;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework.Expression;
using Live2D.Cubism.Framework.MouthMovement;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ciel.EditorTools
{
    public static class CielExpressionPlayCheck
    {
        const string ActiveKey = "Ciel.ExpressionPlayCheck.Active";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/expression-integration/unity-play"));
        static CubismModel _model;
        static CielExpression _expression;
        static CubismExpressionController _controller;
        static CubismMouthController _mouth;
        static Camera _camera;
        static int _index;
        static float _started;
        static StringBuilder _report;

        public static void Run()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
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
                    EditorApplication.Exit(SessionState.GetInt("Ciel.ExpressionPlayCheck.Exit", 1));
                }
            };
        }

        static void Begin()
        {
            try
            {
                Directory.CreateDirectory(OutDir);
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Characters/Ciel/Ciel.prefab");
                var instance = UnityEngine.Object.Instantiate(prefab);
                _model = instance.GetComponent<CubismModel>();
                _expression = instance.GetComponent<CielExpression>() ?? instance.AddComponent<CielExpression>();
                _controller = instance.GetComponent<CubismExpressionController>();
                _mouth = instance.GetComponent<CubismMouthController>();
                _mouth.BlendMode = Live2D.Cubism.Framework.CubismParameterBlendMode.Override;
                _camera = new GameObject("Expression Check Camera", typeof(Camera)).GetComponent<Camera>();
                _camera.orthographic = true;
                _camera.backgroundColor = new Color(0.25f, 0.29f, 0.42f);
                _camera.clearFlags = CameraClearFlags.SolidColor;
                _camera.transform.position = new Vector3(0, 0, -10);
                _camera.orthographicSize = 0.8f;
                _camera.allowHDR = false;
                _camera.GetUniversalAdditionalCameraData().SetRenderer(-1);
                _report = new StringBuilder();
                _index = 0;
                _started = Time.time;
                _expression.Set(CielExpression.Names[0]);
                EditorApplication.update += Tick;
            }
            catch (Exception e) { Finish(e); }
        }

        static float Value(string id)
        {
            var p = Array.Find(_model.Parameters, q => q.Id == id);
            if (p == null) throw new InvalidOperationException("Missing parameter: " + id);
            return p.Value;
        }

        static void Near(string id, float expected)
        {
            if (Mathf.Abs(Value(id) - expected) > 0.02f)
                throw new InvalidOperationException($"{_expression.Current}: {id}={Value(id)}, expected {expected}");
        }

        static void Tick()
        {
            if (!EditorApplication.isPlaying || Time.time - _started < 0.8f) return;
            try
            {
                foreach (var p in _model.Parameters)
                    if (float.IsNaN(p.Value) || float.IsInfinity(p.Value)) throw new InvalidOperationException("Invalid parameter: " + p.Id);
                foreach (var d in _model.Drawables)
                    foreach (var p in d.VertexPositions)
                        if (float.IsNaN(p.x) || float.IsNaN(p.y) || float.IsInfinity(p.x) || float.IsInfinity(p.y))
                            throw new InvalidOperationException("Invalid drawable: " + d.Id);
                var current = _expression.Current;
                // 表情ファイルの値がそのまま出ているか（考え中は通常の値＋目線）。口は口パクが上書きするので別に確かめる
                var file = current == "thinking" ? "neutral" : current;
                var data = Array.Find(_controller.ExpressionsList.CubismExpressionObjects, d => d.name == file + ".exp3");
                if (data == null) throw new InvalidOperationException("Missing expression data: " + file);
                foreach (var p in data.Parameters)
                    if (p.Id != "ParamMouthOpenY") Near(p.Id, p.Value);
                if (current == "thinking") Near("ParamEyeBallX", -0.5f);
                // 表情の最中でも口パクで口が開く
                Near("ParamMouthOpenY", _mouth.MouthOpening);
                if (_index == CielExpression.Names.Length && current != "neutral") throw new InvalidOperationException("TTL did not reset to neutral");
                _report.AppendLine($"{_index}: {current} OK mouth={Value("ParamMouthOpenY"):0.00}");
                Shot(_index == CielExpression.Names.Length ? "ttl-neutral" : current);
                _index++;
                if (_index > CielExpression.Names.Length) { Finish(null); return; }
                _started = Time.time;
                _mouth.MouthOpening = _index % 2 == 1 ? 0.8f : 0f;   // 半分は話している最中として確かめる
                if (_index == CielExpression.Names.Length) _expression.Set("happy", 0.1f);
                else _expression.Set(CielExpression.Names[_index]);
            }
            catch (Exception e) { Finish(e); }
        }

        static void Shot(string name)
        {
            // Editor render requests run outside the usual camera update callback.
            _model.ForceUpdateNow();
            // Each diagnostic shot has a new target: rebuild Cubism's cached
            // render groups so CurrentFrameBuffer uses this request's handle.
            Live2D.Cubism.Rendering.CubismRenderControllerGroup.GetInstance().SortingRenderControllerGroups();
            var target = new RenderTexture(540, 720, 24);
            var previous = RenderTexture.active;
            var texture = new Texture2D(540, 720, TextureFormat.RGB24, false);
            try
            {
                _camera.targetTexture = target;
                RenderPipeline.SubmitRenderRequest(_camera, new UniversalRenderPipeline.SingleCameraRequest { destination = target });
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, 540, 720), 0, 0);
                int visiblePixels = 0;
                var background = _camera.backgroundColor;
                foreach (var pixel in texture.GetPixels())
                    if (Mathf.Abs(pixel.r - background.r) + Mathf.Abs(pixel.g - background.g) + Mathf.Abs(pixel.b - background.b) > 0.15f) visiblePixels++;
                _report.AppendLine($"render {name}: {visiblePixels} foreground pixels");
                if (visiblePixels < 1000)
                {
                    foreach (var renderer in _model.GetComponentsInChildren<Live2D.Cubism.Rendering.CubismRenderer>())
                        _report.AppendLine($"{renderer.name}: meshBounds={renderer.Mesh?.bounds} nativeFirst={renderer.Drawable?.VertexPositions[0]} material={renderer.DrawMaterial?.name}");
                    throw new InvalidOperationException("Model was not visible in Unity: " + name);
                }
                File.WriteAllBytes(Path.Combine(OutDir, name + ".png"), texture.EncodeToPNG());
            }
            finally
            {
                _camera.targetTexture = null;
                RenderTexture.active = previous;
                target.Release();
                UnityEngine.Object.Destroy(texture);
                UnityEngine.Object.Destroy(target);
            }
        }

        static void Finish(Exception error)
        {
            EditorApplication.update -= Tick;
            Directory.CreateDirectory(OutDir);
            File.WriteAllText(Path.Combine(OutDir, "verification.txt"), (_report?.ToString() ?? "") + (error?.ToString() ?? "12 expressions + TTL passed"));
            if (error == null) Debug.Log("CIEL_EXPRESSION_PLAY_CHECK_DONE");
            else Debug.LogException(error);
            SessionState.SetInt("Ciel.ExpressionPlayCheck.Exit", error == null ? 0 : 1);
            EditorApplication.ExitPlaymode();
        }
    }
}
