using System;
using System.IO;
using System.Reflection;
using Ciel.Conversation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.EditorTools
{
    public static class CielAudienceCardCheck
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        static int _checks;
        static void Check(bool ok, string name)
        {
            if (!ok) throw new InvalidOperationException("Audience card: " + name);
            _checks++;
        }
        static void Invoke(object target, string method) => target.GetType().GetMethod(method, Private).Invoke(target, null);

        public static void Run()
        {
            _checks = 0;
            var goal = new CielConversation.GoalState {
                v = 2, type = "goal.state", stream_id = "stream", revision = 1, has_task = true,
                confirmed = true, valid_for_ms = 10000, receivedAt = Time.unscaledTime,
                task = new CielConversation.WorkInfo { session = "server", task_id = "task", revision = 1,
                    title = "鉄を10個集める", state = "running", can_stop = true, remaining_known = true, remaining_ms = 45000 }
            };
            var activity = new CielConversation.ActivityState { mind = "speaking", detail_version = 1,
                body = new CielConversation.ActivityBody { version = 1, phase = "running", title = "鉄鉱石を探している" } };
            var state = CielAudienceCardState.From(goal, activity, true, false);
            Check(state.visible && state.title == goal.task.title && state.conversation.Contains("話しています"), "work and conversation coexist");
            Check(state.progress.Contains("予算") && state.fraction < 0, "budget is not progress");
            Render(state, "audience-card-work-v2", false);
            foreach (var phase in new[] { "accepted", "running", "needs_decision", "cancelling", "succeeded", "failed", "cancelled" })
            {
                goal.task.state = phase;
                var view = CielWorkPresentation.From(goal);
                Check(view.phase == phase, "preserve state " + phase);
                Check(!view.Summary.Contains("0/0"), "no fabricated steps " + phase);
            }
            goal.task.state = "needs_decision";
            goal.task.decision_id = "decision";
            goal.task.decision_message = "材料がありません。再試行しますか？";
            goal.task.can_retry = true;
            Check(CielWorkPresentation.From(goal).canRetry, "confirmed decision allows retry");
            state = CielAudienceCardState.From(goal, activity, true, false);
            Check(state.phase == "needs_decision" && state.current.Contains("材料"), "decision reason");
            Render(state, "audience-card-decision-v2", false);
            goal.task.state = "cancelling";
            Check(!CielWorkPresentation.From(goal).canRetry && !CielWorkPresentation.From(goal).canStop, "no controls during cancellation");
            Check(CielWorkPresentation.From(goal).status == "停止確認中", "cancelling is not stopped");
            goal.task.state = "running";
            goal.receivedAt = Time.unscaledTime - 11;
            var stale = CielWorkPresentation.From(goal);
            Check(stale.phase == "unknown" && stale.canStop && !stale.canRetry && stale.budget == "", "lease expiry retains targeted stop");
            Render(CielAudienceCardState.From(goal, activity, true, false), "audience-card-unknown-v2", false);
            goal.receivedAt = Time.unscaledTime;
            Check(CielWorkPresentation.From(goal).phase == "running", "fresh confirmation recovers");
            goal.task.state = "succeeded";
            goal.receivedAt -= 11;
            Check(CielWorkPresentation.From(goal).phase == "succeeded", "terminal fact survives lease expiry");
            Check(!CielWorkPresentation.From(goal).canStop, "no terminal stop");
            var idle = new CielConversation.ActivityState { mind = "listening", detail_version = 1,
                body = new CielConversation.ActivityBody { version = 1, phase = "idle" } };
            Check(CielAudienceCardState.From(goal, idle, true, true).heading.Contains("できた"), "brief completion");
            Check(CielAudienceCardState.From(goal, idle, true, false).phase == "idle", "completion expires");
            Check(CielAudienceCardState.From(null, activity, true, false).visible, "direct work remains visible");
            Check(CielAudienceCardState.From(goal, activity, false, true).phase == "disconnected", "disconnect explicit");
            Check(CielAudienceCardState.From(null, null, true, false).phase == "unknown", "missing state not idle");
            Check(CielAudienceCardState.Conversation(new CielConversation.ActivityState { mind = "thinking", thinking_origin = "comment" }).Contains("コメント"), "reaction origin");
            CielAppCompositionCheck.Run();
            Debug.Log("CIEL_AUDIENCE_CARD_CHECK_OK " + _checks);
        }

        static void Render(CielAudienceCardState state, string name, bool native)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var main = new GameObject("Main Camera", typeof(Camera)); main.tag = "MainCamera";
            var go = new GameObject("Card Check", typeof(CielAudienceCard));
            var card = go.GetComponent<CielAudienceCard>();
            Invoke(card, "Awake");
            card.Show(state);
            Check((main.GetComponent<Camera>().cullingMask & (1 << CielAudienceCard.Layer)) == 0, "main camera excludes card");
            foreach (var text in go.GetComponentsInChildren<Text>(true)) Check(!text.supportRichText, "plain text prevents markup injection");
            var camera = go.transform.Find("Card Source Camera").GetComponent<Camera>();
            Check(camera.cullingMask == 1 << CielAudienceCard.Layer && camera.GetComponent<AudioListener>() == null, "isolated output without audio");
            if (SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                var target = new RenderTexture(900, 500, 24);
                camera.targetTexture = target; camera.aspect = 1.8f;
                Canvas.ForceUpdateCanvases(); camera.Render();
                RenderTexture.active = target;
                var image = new Texture2D(900, 500, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, 900, 500), 0, 0); image.Apply();
                var dir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/app-refactor"));
                Directory.CreateDirectory(dir);
                File.WriteAllBytes(Path.Combine(dir, name + ".png"), image.EncodeToPNG());
                card.Show(new CielAudienceCardState()); camera.Render();
                image.ReadPixels(new Rect(0, 0, 900, 500), 0, 0); image.Apply();
                var pixel = image.GetPixel(450, 250);
                Check(pixel.g < .5f, "idle keeps the card background instead of flashing green");
                RenderTexture.active = null; camera.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(image); target.Release(); UnityEngine.Object.DestroyImmediate(target);
                if (native) CheckNativeWindows(card);
            }
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        static void CheckNativeWindows(CielAudienceCard card)
        {
            var keys = new[] { "ciel.streamWindow.width", "ciel.streamWindow.height", "ciel.statusCard.width", "ciel.statusCard.height" };
            var values = Array.ConvertAll(keys, key => PlayerPrefs.HasKey(key) ? (int?)PlayerPrefs.GetInt(key) : null);
            var avatarObject = new GameObject("Avatar Output Check", typeof(CielStreamWindow));
            var avatar = avatarObject.GetComponent<CielStreamWindow>();
            try
            {
                Invoke(avatar, "Open"); Invoke(card.Output, "Open");
                Check(avatar.IsOpen && card.Output.IsOpen, "two native windows coexist");
                Invoke(card.Output, "Close");
                Check(avatar.IsOpen && !card.Output.IsOpen, "closing card preserves avatar");
                Invoke(card.Output, "Open"); Check(card.Output.IsOpen, "card reopens");
                Invoke(avatar, "Close");
                Check(!avatar.IsOpen && card.Output.IsOpen, "closing avatar preserves card");
            }
            finally
            {
                Invoke(avatar, "Close"); Invoke(card.Output, "Close");
                UnityEngine.Object.DestroyImmediate(avatarObject);
                for (int i = 0; i < keys.Length; i++)
                    if (values[i].HasValue) PlayerPrefs.SetInt(keys[i], values[i].Value); else PlayerPrefs.DeleteKey(keys[i]);
            }
        }
    }
}
