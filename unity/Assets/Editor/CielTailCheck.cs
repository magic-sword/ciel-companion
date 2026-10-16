using System;
using System.Collections;
using System.IO;
using System.Linq;
using System.Reflection;
using Ciel.Conversation;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    // Opt-in integration check: place .local/tail-play-check/request and launch
    // the editor without batch mode. No conversation connection is made.
    [InitializeOnLoad]
    public static class CielTailCheck
    {
        public static string Output => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/tail-play-check"));
        static string Request => Path.Combine(Output, "request");
        const string Key = "CielTailCheck.stage";
        static CielTailCheck() => EditorApplication.update += Poll;
        static void Poll()
        {
            if (!File.Exists(Request) || EditorApplication.isCompiling || EditorApplication.isUpdating) return;
            int stage = SessionState.GetInt(Key, 0);
            if (stage == 3 && !EditorApplication.isPlaying)
            {
                var passed = SessionState.GetBool(Key + ".passed", false);
                SessionState.EraseInt(Key);SessionState.EraseInt(Key + ".size");
                SessionState.EraseBool(Key + ".passed");File.Delete(Request);
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                EditorApplication.Exit(passed ? 0 : 1);return;
            }
            if (stage == 0 && !EditorApplication.isPlaying && EditorApplication.timeSinceStartup > 20)
            {
                EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
                foreach (var c in UnityEngine.Object.FindObjectsByType<CielConversation>())
                {
                    var so = new SerializedObject(c);
                    so.FindProperty("_connectOnStart").boolValue = false;
                    so.ApplyModifiedPropertiesWithoutUndo();
                }
                int size = (int)typeof(CielPlayModeShot).GetMethod("SetGameViewSize", BindingFlags.Static | BindingFlags.NonPublic)
                    .Invoke(null, new object[] { 540, 1170 });
                SessionState.SetInt(Key + ".size", size);
                SessionState.SetInt(Key, 1);
                EditorApplication.isPlaying = true;
            }
            else if (stage == 1 && EditorApplication.isPlaying)
            {
                SessionState.SetInt(Key, 2);
                new GameObject("TailPlaybackCheck").AddComponent<CielTailProbe>();
            }
        }
        public static void Finish(bool passed)
        {
            // Unity 6.6 expects the absolute size index here.
            var args = new object[] { null };
            var group = typeof(CielPlayModeShot).GetMethod("SizeGroup", BindingFlags.Static | BindingFlags.NonPublic).Invoke(null, args);
            group.GetType().GetMethod("RemoveCustomSize").Invoke(group, new object[] { SessionState.GetInt(Key + ".size", -1) });
            SessionState.SetInt(Key, 3);SessionState.SetBool(Key + ".passed", passed);
            EditorApplication.isPlaying = false;
        }
    }

    public sealed class CielTailProbe : MonoBehaviour
    {
        IEnumerator Start()
        {
            yield return new WaitForSeconds(2f);
            var tail = FindAnyObjectByType<CielTail>();
            var model = tail != null ? tail.GetComponent<CubismModel>() : null;
            if (model == null) { Fail("No tail component/model");yield break; }
            var wag = Array.Find(model.Parameters, p => p.Id == "ParamCielTailWag");
            var follow = Array.Find(model.Parameters, p => p.Id == "ParamCielTailFollow");
            var tip = Array.Find(model.Parameters, p => p.Id == "ParamCielTailTip");
            if (wag == null || follow == null || tip == null) { Fail("Missing tail parameters");yield break; }
            float neutral = wag.Value;
            var camera = Camera.main;
            File.WriteAllText(Path.Combine(CielTailCheck.Output, "camera.json"),
                FormattableString.Invariant($"{{\"orthographic_size\":{camera.orthographicSize},\"position\":[{camera.transform.position.x},{camera.transform.position.y}]}}"));
            ScreenCapture.CaptureScreenshot(Path.Combine(CielTailCheck.Output, "neutral.png"));
            tail.Wag(1f, 3f, 1.2f);
            float start = Time.time, min = 0, max = 0, fmax = 0, tmax = 0;
            bool left = false, right = false;
            var frames = Path.Combine(CielTailCheck.Output, "frames");Directory.CreateDirectory(frames);
            float nextShot = .6f;int shot = 0;
            var csv = new System.Text.StringBuilder("t,wag,follow,tip\n");
            while (Time.time - start < 3f)
            {
                yield return new WaitForEndOfFrame();
                min = Mathf.Min(min, wag.Value);max = Mathf.Max(max, wag.Value);
                fmax = Mathf.Max(fmax, Mathf.Abs(follow.Value));tmax = Mathf.Max(tmax, Mathf.Abs(tip.Value));
                csv.AppendLine(FormattableString.Invariant($"{Time.time-start:F4},{wag.Value:F5},{follow.Value:F5},{tip.Value:F5}"));
                if (Time.time-start >= nextShot && Time.time-start < 2.6f)
                {
                    ScreenCapture.CaptureScreenshot(Path.Combine(frames, $"{shot++:D3}.png"));
                    nextShot += 1f/12f;
                }
                if (!left && wag.Value < -.95f) { ScreenCapture.CaptureScreenshot(Path.Combine(CielTailCheck.Output, "left.png"));left = true; }
                if (!right && wag.Value > .95f) { ScreenCapture.CaptureScreenshot(Path.Combine(CielTailCheck.Output, "right.png"));right = true; }
            }
            yield return new WaitForSeconds(4f);
            float settled = wag.Value;
            var expression = tail.GetComponent<CielExpression>();
            if (expression != null) expression.Set("happy");
            yield return new WaitForSeconds(1f);
            float happyMax = 0;
            start = Time.time;
            while (Time.time-start < 1f) { yield return new WaitForEndOfFrame();happyMax = Mathf.Max(happyMax, Mathf.Abs(wag.Value)); }
            ScreenCapture.CaptureScreenshot(Path.Combine(CielTailCheck.Output, "happy.png"));
            if (expression != null) expression.Set("neutral");
            bool passed = Mathf.Abs(neutral) < .001f && min < -.8f && max > .8f
                && fmax > .001f && fmax < .95f && tmax > .001f && tmax < .95f
                && Mathf.Abs(settled) < .001f && happyMax > .7f;
            File.WriteAllText(Path.Combine(CielTailCheck.Output, "samples.csv"), csv.ToString());
            File.WriteAllText(Path.Combine(CielTailCheck.Output, "result.json"),
                FormattableString.Invariant($"{{\"passed\":{passed.ToString().ToLowerInvariant()},\"neutral\":{neutral},\"wag_min\":{min},\"wag_max\":{max},\"follow_max\":{fmax},\"tip_max\":{tmax},\"settled\":{settled},\"happy_max\":{happyMax},\"screen\":\"{Screen.width}x{Screen.height}\"}}"));
            yield return new WaitForSeconds(.5f);
            Debug.Log("CIEL_TAIL_PLAY_CHECK " + passed);
            CielTailCheck.Finish(passed);
        }
        void Fail(string message)
        {
            File.WriteAllText(Path.Combine(CielTailCheck.Output, "failure.txt"), message);
            Debug.LogError(message);CielTailCheck.Finish(false);
        }
    }
}
