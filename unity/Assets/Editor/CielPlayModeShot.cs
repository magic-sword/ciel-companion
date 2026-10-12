// 会話シーンを実際の再生モードで動かし、ゲームのカメラの映りを数回撮る（会話の接続はしない）。
// 使い方：.local/render-check/playmode-request を置いて、エディタを起動する（-batchmode は付けない）。
// 出力：.local/render-check/playmode-*.png と playmode.txt。終わるとエディタを終了する。
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    [InitializeOnLoad]
    public static class CielPlayModeShot
    {
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/render-check"));
        static string RequestPath => Path.Combine(OutDir, "playmode-request");
        const string Key = "CielPlayModeShot.step";

        static CielPlayModeShot()
        {
            EditorApplication.update += Poll;
        }

        static double _t0;
        static bool _refreshed;

        static void Poll()
        {
            if (!File.Exists(RequestPath)) return;
            var step = SessionState.GetInt(Key, 0);
            if (step == 0 && !EditorApplication.isPlaying)
            {
                // 起動直後の読み込み・コンパイルが落ち着いてから再生する（途中で再読み込みが起きないように）
                if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.timeSinceStartup < 20) return;
                if (!_refreshed) { _refreshed = true; AssetDatabase.Refresh(); return; }
                SessionState.SetInt(Key, 1);
                EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
                foreach (var c in Object.FindObjectsByType<Ciel.Conversation.CielConversation>())
                {
                    var so = new SerializedObject(c);
                    so.FindProperty("_connectOnStart").boolValue = File.ReadAllText(RequestPath).Contains("connect");
                    so.ApplyModifiedPropertiesWithoutUndo();
                }
                EditorApplication.isPlaying = true;
                return;
            }
            if (step == 1 && EditorApplication.isPlaying)
            {
                SessionState.SetInt(Key, 2);
                _t0 = EditorApplication.timeSinceStartup;
                var grab = new GameObject("CielScreenGrab").AddComponent<Ciel.Diagnostics.CielScreenGrab>();
                grab.gameObject.AddComponent<Ciel.Diagnostics.CielFrameTrace>();
                grab.OutDir = OutDir;
                return;
            }
            if (step >= 2 && step < 5 && EditorApplication.isPlaying)
            {
                var t = EditorApplication.timeSinceStartup - _t0;
                if (t < (step - 1) * 1.5) return;
                var cam = Camera.main;
                var rt = new RenderTexture(270, 480, 24);
                cam.targetTexture = rt;
                cam.Render();
                RenderTexture.active = rt;
                var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
                cam.targetTexture = null;
                RenderTexture.active = null;
                File.WriteAllBytes(Path.Combine(OutDir, $"playmode-{step}.png"), tex.EncodeToPNG());
                File.AppendAllText(Path.Combine(OutDir, "playmode.txt"), $"step={step} t={t:0.0} frame={Time.frameCount}\n");
                SessionState.SetInt(Key, step + 1);
                return;
            }
            if (step == 5)
            {
                var g = Object.FindAnyObjectByType<Ciel.Diagnostics.CielScreenGrab>();
                if (g != null && !g.Done && EditorApplication.timeSinceStartup - _t0 < 30) return;
                SessionState.SetInt(Key, 6);
                File.Delete(RequestPath);
                EditorApplication.isPlaying = false;
                EditorApplication.delayCall += () => EditorApplication.Exit(0);
            }
        }
    }
}
