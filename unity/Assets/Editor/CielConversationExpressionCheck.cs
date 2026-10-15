// アプリの会話シーン（Conversation.unity）を再生し、会話サーバーと同じ表情のイベント（ciel.event の JSON）を
// CielConversation に渡して、表情ファイルの値が出ること・寿命で通常へ戻ることを確かめる。ネットワークには接続しない。
// Unity.exe -projectPath unity -executeMethod Ciel.EditorTools.CielConversationExpressionCheck.Run -logFile <log>
// （-batchmode では再生モードに入らないので付けない。終わるとエディタを終了する）
// 出力：.local/expression-integration/conversation/*.png と verification.txt
using System;
using System.IO;
using System.Reflection;
using System.Text;
using Ciel.Conversation;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework.Expression;
using LiveKit.Proto;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Ciel.EditorTools
{
    public static class CielConversationExpressionCheck
    {
        const string ActiveKey = "Ciel.ConversationExpressionCheck.Active";
        const string ExitKey = "Ciel.ConversationExpressionCheck.Exit";
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/expression-integration/conversation"));
        static CielConversation _conversation;
        static CielExpression _expression;
        static CubismExpressionController _controller;
        static CubismModel _model;
        static MethodInfo _receive;
        static int _index, _seq;
        static float _started;
        static StringBuilder _report;

        public static void Run()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
            // 保存はしない。再生中だけ接続を止める
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
            try
            {
                Directory.CreateDirectory(OutDir);
                _conversation = UnityEngine.Object.FindAnyObjectByType<CielConversation>();
                if (_conversation == null) throw new InvalidOperationException("No CielConversation in the scene.");
                var field = typeof(CielConversation).GetField("_expression", BindingFlags.Instance | BindingFlags.NonPublic);
                _expression = (CielExpression)field.GetValue(_conversation);
                if (_expression == null) throw new InvalidOperationException("CielConversation has no expression reference.");
                _model = _expression.GetComponent<CubismModel>();
                _controller = _expression.GetComponent<CubismExpressionController>();
                if (_controller == null || _controller.ExpressionsList == null) throw new InvalidOperationException("Model has no expression list.");
                _receive = typeof(CielConversation).GetMethod("OnDataReceived", BindingFlags.Instance | BindingFlags.NonPublic);
                _report = new StringBuilder();
                _index = 0;
                // 違う topic と知らない表情は無視される
                Send("happy", 5000, "other.topic");
                Send("unknown", 5000);
                if (_expression.Current != "neutral") throw new InvalidOperationException("Ignored event changed the expression: " + _expression.Current);
                Send(CielExpression.Names[0], 2000);
                _started = Time.time;
                EditorApplication.update += Tick;
            }
            catch (Exception e) { Finish(e); }
        }

        // 会話サーバー（server/agent/emotion.py）と同じ形の JSON
        static void Send(string expression, int ttlMs, string topic = "ciel.event")
        {
            _seq++;
            var json = $"{{\"v\": 1, \"type\": \"character.expression\", \"seq\": {_seq}, \"expression\": \"{expression}\", \"intensity\": 1.0, \"ttl_ms\": {ttlMs}}}";
            _receive.Invoke(_conversation, new object[] { Encoding.UTF8.GetBytes(json), null, DataPacketKind.KindReliable, topic });
        }

        static float Value(string id)
        {
            var p = Array.Find(_model.Parameters, q => q.Id == id);
            if (p == null) throw new InvalidOperationException("Missing parameter: " + id);
            return p.Value;
        }

        static void Tick()
        {
            if (!EditorApplication.isPlaying || Time.time - _started < 0.8f) return;
            try
            {
                var names = CielExpression.Names;
                var expected = _index < names.Length ? names[_index] : "neutral";
                var current = _expression.Current;
                if (current != expected) throw new InvalidOperationException($"Expected {expected}, got {current}");
                var file = current == "thinking" ? "neutral" : current;
                var data = Array.Find(_controller.ExpressionsList.CubismExpressionObjects, d => d.name == file + ".exp3");
                if (data == null) throw new InvalidOperationException("Missing expression data: " + file);
                foreach (var p in data.Parameters)
                    if (p.Id != "ParamMouthOpenY" && Mathf.Abs(Value(p.Id) - p.Value) > 0.02f)
                        throw new InvalidOperationException($"{current}: {p.Id}={Value(p.Id)}, expected {p.Value}");
                _report.AppendLine($"{_index}: {current} OK");
                Shot(_index < names.Length ? current : "ttl-neutral");
                _index++;
                if (_index > names.Length) { Finish(null); return; }
                _started = Time.time;
                // 最後は短い寿命の表情を送り、通常へ戻るのを待つ
                if (_index == names.Length) Send("excited", 300);
                else Send(names[_index], 2000);
            }
            catch (Exception e) { Finish(e); }
        }

        static void Shot(string name)
        {
            var camera = Camera.main;
            _model.ForceUpdateNow();
            Live2D.Cubism.Rendering.CubismRenderControllerGroup.GetInstance().SortingRenderControllerGroups();
            var target = new RenderTexture(540, 960, 24);
            var previous = RenderTexture.active;
            var texture = new Texture2D(540, 960, TextureFormat.RGB24, false);
            try
            {
                camera.targetTexture = target;
                RenderPipeline.SubmitRenderRequest(camera, new UniversalRenderPipeline.SingleCameraRequest { destination = target });
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, 540, 960), 0, 0);
                int visible = 0;
                var background = camera.backgroundColor;
                foreach (var pixel in texture.GetPixels())
                    if (Mathf.Abs(pixel.r - background.r) + Mathf.Abs(pixel.g - background.g) + Mathf.Abs(pixel.b - background.b) > 0.15f) visible++;
                _report.AppendLine($"render {name}: {visible} foreground pixels");
                if (visible < 1000) throw new InvalidOperationException("Ciel was not visible: " + name);
                File.WriteAllBytes(Path.Combine(OutDir, name + ".png"), texture.EncodeToPNG());
            }
            finally
            {
                camera.targetTexture = null;
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
                (_report?.ToString() ?? "") + (error?.ToString() ?? "conversation events: 12 expressions + ignored events + TTL passed"));
            if (error == null) Debug.Log("CIEL_CONVERSATION_EXPRESSION_CHECK_DONE");
            else Debug.LogException(error);
            SessionState.SetInt(ExitKey, error == null ? 0 : 1);
            EditorApplication.ExitPlaymode();
        }
    }
}
