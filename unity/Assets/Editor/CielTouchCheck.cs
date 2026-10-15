// 会話シーンを再生し、シエルの各部位に触れたときの判定・体の反応・髪の物理演算の揺れを確かめる。ネットワークには接続しない。
// Unity.exe -projectPath unity -executeMethod Ciel.EditorTools.CielTouchCheck.Run -logFile <log>
// （-batchmode では再生モードに入らないので付けない。終わるとエディタを終了する）
// 出力：.local/touch-check/*.png と verification.txt
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
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ciel.EditorTools
{
    public static class CielTouchCheck
    {
        const string ActiveKey = "Ciel.TouchCheck.Active";
        const string ExitKey = "Ciel.TouchCheck.Exit";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/touch-check"));

        // 触れる部品・しぐさ・期待する部位
        static readonly (string name, string drawable, string gesture, CielTouch.Part part)[] Cases =
        {
            ("head-stroke", "Hair_Crown", "stroke", CielTouch.Part.Head),
            ("ear-tap", "Ear_R_Outer", "tap", CielTouch.Part.Ear),
            ("cheek-tap", "Face_Skin", "tap", CielTouch.Part.Face),
            ("hair-stroke", "Hair_Side_R_LongFront", "stroke", CielTouch.Part.Hair),
            ("shoulder-tap", "Jacket48_Fur_R", "tap", CielTouch.Part.Shoulder),
            ("hand-tap", "Body48_HandRelaxed_R", "tap", CielTouch.Part.Hand),
            ("chest-tap", "Body48_Torso", "tap", CielTouch.Part.None),
        };

        static CielTouch _touch;
        static CielExpression _expression;
        static CubismModel _model;
        static Camera _camera;
        static int _case;
        static float _caseStart;
        static int _step;
        static Vector2 _point;
        static string _lastTouchBefore;
        static readonly Dictionary<string, float> Peak = new Dictionary<string, float>();
        static StringBuilder _report;

        public static void Run()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
            foreach (var c in UnityEngine.Object.FindObjectsByType<CielConversation>())
            {
                var so = new SerializedObject(c);
                so.FindProperty("_connectOnStart").boolValue = false;   // 保存しない。再生中だけ接続を止める
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
            try
            {
                Directory.CreateDirectory(OutDir);
                foreach (var f in Directory.GetFiles(OutDir, "*.png")) File.Delete(f);
                _touch = UnityEngine.Object.FindAnyObjectByType<CielTouch>();
                if (_touch == null) throw new InvalidOperationException("No CielTouch in the conversation scene.");
                _model = _touch.GetComponent<CubismModel>();
                _expression = _touch.GetComponent<CielExpression>();
                _camera = Camera.main;
                _report = new StringBuilder();
                _case = -1;
                _caseStart = Time.time + 1.5f;   // 物理演算が落ち着くのを待つ
                EditorApplication.update += Tick;
            }
            catch (Exception e) { Finish(e); }
        }

        static float Value(string id) => _model.Parameters.First(p => p.Id == id).Value;

        // 部品の範囲から、その部位として判定される画面の点を探す（手前の部品に隠れていない点）
        static Vector2 FindPoint(string drawableId, CielTouch.Part expected)
        {
            var d = _model.Drawables.First(x => x.Id == drawableId);
            // 今の頂点の範囲（描画の範囲は更新されないことがある）
            Vector2 lo = Vector2.positiveInfinity, hi = Vector2.negativeInfinity;
            foreach (var v in d.VertexPositions)
            {
                Vector2 sp = _camera.WorldToScreenPoint(d.transform.TransformPoint(v));
                lo = Vector2.Min(lo, sp); hi = Vector2.Max(hi, sp);
            }
            var best = new List<Vector2>();
            for (int i = 1; i < 16; i++)
                for (int j = 1; j < 16; j++)
                {
                    var p = new Vector2(Mathf.Lerp(lo.x, hi.x, i / 16f), Mathf.Lerp(lo.y, hi.y, j / 16f));
                    if (_touch.PartAt(p) == expected) best.Add(p);
                }
            if (best.Count == 0)
            {
                var center = (Vector2)_camera.WorldToScreenPoint(CielTouch.Center(d));
                throw new InvalidOperationException($"No touchable point on {drawableId} as {expected}; screen={Screen.width}x{Screen.height} center={center} {_touch.DescribeAt(center)}");
            }
            // 見つかった点の中央付近を使う
            var mean = best.Aggregate(Vector2.zero, (a, p) => a + p) / best.Count;
            return best.OrderBy(p => (p - mean).sqrMagnitude).First();
        }

        static void Tick()
        {
            if (!EditorApplication.isPlaying) return;
            try
            {
                var t = Time.time - _caseStart;
                if (t < 0) return;
                if (_case < 0) { NextCase(); return; }
                var c = Cases[_case];
                foreach (var id in new[] { "ParamHairSide", "ParamHairFront", "ParamCielFurSwingR", "ParamCielFurSwingL", "ParamEar", "ParamAngleY", "ParamAngleX", "ParamEyeBallX" })
                    Peak[id] = Mathf.Max(Peak.TryGetValue(id, out var v) ? v : 0f, Mathf.Abs(Value(id)));

                if (_step == 0)
                {
                    _point = FindPoint(c.drawable, c.part);
                    _lastTouchBefore = _touch.LastTouch;
                    Peak.Clear();
                    _touch.Press(_point);
                    _step = 1;
                    return;
                }
                if (_step == 1)
                {
                    if (c.gesture == "stroke" && t < 1.6f)
                    {
                        // 左右に往復してなぞる（画面の高さの約 6%）
                        var x = Mathf.Sin(t * 9f) * Screen.height * 0.03f;
                        _touch.Drag(_point + new Vector2(x, 0));
                        if (t > 1.2f && !File.Exists(Path.Combine(OutDir, c.name + ".png"))) Shot(c.name);
                        return;
                    }
                    if (c.gesture == "tap" && t < 0.1f) return;
                    _touch.Release();
                    _step = 2;
                    return;
                }
                if (_step == 2 && t < 2.6f)
                {
                    if (c.gesture == "tap" && t > 0.5f && !File.Exists(Path.Combine(OutDir, c.name + ".png"))) Shot(c.name);
                    return;
                }

                // 判定と反応を確かめる
                var expectedName = c.part == CielTouch.Part.None ? _lastTouchBefore : $"{PartName(c.part)}/{c.gesture}/{(c.gesture == "stroke" ? "end" : "once")}";
                if (_touch.LastTouch != expectedName) throw new InvalidOperationException($"{c.name}: touch {_touch.LastTouch}, expected {expectedName}");
                var peaks = string.Join(" ", Peak.Select(kv => $"{kv.Key}={kv.Value:0.00}"));
                _report.AppendLine($"{c.name}: {_touch.LastTouch} expression={_expression.Current} {peaks}");
                switch (c.name)
                {
                    case "head-stroke": Require(Peak["ParamAngleY"] > 3f, "head did not dip while stroked"); break;
                    case "hair-stroke": Require(Peak["ParamHairSide"] > 0.15f, "side hair did not swing"); break;
                    case "shoulder-tap": Require(Peak["ParamCielFurSwingR"] > 0.2f, "touched (right) shoulder fur did not swing"); break;
                    case "ear-tap": Require(Peak["ParamEar"] > 0.2f, "ear did not twitch"); break;
                }
                NextCase();
            }
            catch (Exception e) { Finish(e); }
        }

        static void Require(bool ok, string message)
        {
            if (!ok) throw new InvalidOperationException(message);
        }

        static string PartName(CielTouch.Part p) => p.ToString().ToLowerInvariant();

        static void NextCase()
        {
            _case++;
            _step = 0;
            _caseStart = Time.time + 0.8f;   // 前の揺れが収まるのを少し待つ
            if (_case >= Cases.Length) Finish(null);
        }

        static void Shot(string name)
        {
            _model.ForceUpdateNow();
            Live2D.Cubism.Rendering.CubismRenderControllerGroup.GetInstance().SortingRenderControllerGroups();
            int w = Screen.width, h = Screen.height;   // 触れた点と同じ座標で撮る
            var target = new RenderTexture(w, h, 24);
            var previous = RenderTexture.active;
            var texture = new Texture2D(w, h, TextureFormat.RGB24, false);
            try
            {
                _camera.targetTexture = target;
                RenderPipeline.SubmitRenderRequest(_camera, new UniversalRenderPipeline.SingleCameraRequest { destination = target });
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, w, h), 0, 0);
                // 触れた点に印を付ける
                var px = _point;
                for (int dx = -6; dx <= 6; dx++)
                    for (int dy = -6; dy <= 6; dy++)
                        if (Mathf.Abs(dx * dx + dy * dy - 25) < 8) texture.SetPixel((int)px.x + dx, (int)px.y + dy, Color.red);
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
            File.WriteAllText(Path.Combine(OutDir, "verification.txt"),
                (_report?.ToString() ?? "") + (error?.ToString() ?? $"touch: {Cases.Length} cases passed"));
            if (error == null) Debug.Log("CIEL_TOUCH_CHECK_DONE");
            else Debug.LogException(error);
            SessionState.SetInt(ExitKey, error == null ? 0 : 1);
            EditorApplication.ExitPlaymode();
        }
    }
}
