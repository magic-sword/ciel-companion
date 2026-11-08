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
                goal = new CielConversation.GoalInfo { id = 1, title = "鉄を10個集める", status = "running", by_label = "非公開の名前" },
                steps = new[] { new CielConversation.GoalStep { label = "鉄を集める", status = "running", progress = new[] { 3, 10 } } }
            };
            var activity = new CielConversation.ActivityState { tasks = new[] { new CielConversation.ActivityTask { title = "鉄鉱石を探している" } } };
            var state = CielAudienceCardState.From(goal, activity, true, false);
            Check(state.visible && state.title == goal.goal.title && state.current.Contains(activity.tasks[0].title), "objective and current work");
            Check(state.progress == "現在の手順：3 / 10" && Math.Abs(state.fraction - .3f) < .001, "received progress");
            Check(!(state.heading + state.title + state.current + state.progress).Contains("非公開"), "owner name excluded");
            Render(state, "audience-card-progress", true);
            goal.steps[0].progress = null;
            Check(CielAudienceCardState.From(goal, activity, true, false).progress == "手順完了：0 / 1", "step count labelled");
            goal.steps = null;
            Check(CielAudienceCardState.From(goal, activity, true, false).fraction < 0, "unknown progress not invented");
            goal.goal.status = "paused";
            goal.attention = "石のツルハシの材料が足りない";
            state = CielAudienceCardState.From(goal, activity, true, false);
            Check(state.attention && state.current == goal.attention, "pause reason");
            Render(state, "audience-card-paused", false);
            goal.goal.status = "done";
            Check(CielAudienceCardState.From(goal, activity, true, true).title == activity.tasks[0].title, "next direct task replaces completed goal");
            Check(CielAudienceCardState.From(null, activity, true, false).visible, "task without goal");
            var idle = new CielConversation.ActivityState { detail_version = 1, mind = "listening", log = new[] { new CielConversation.ActivityLog { text = "内部ログ" } } };
            state = CielAudienceCardState.From(null, idle, true, false);
            Check(state.visible && state.phase == "idle" && !state.current.Contains("内部ログ"), "idle remains visible without internal logs");
            Render(state, "audience-card-idle", false);
            state = CielAudienceCardState.From(goal, activity, false, true);
            Check(state.visible && state.phase == "disconnected" && !state.title.Contains("鉄"), "disconnect is explicit without stale work");
            Check(CielAudienceCardState.From(goal, idle, true, true).current == "できた！", "brief completion");
            Check(CielAudienceCardState.From(goal, idle, true, false).phase == "idle", "completion returns to visible idle");
            var thinking = new CielConversation.ActivityState { mind = "thinking", mind_for = 4, thinking_origin = "reply" };
            state = CielAudienceCardState.From(null, thinking, true, false, 3);
            Check(state.phase == "thinking" && state.elapsed == "7秒経過", "thinking timer advances without another message");
            Render(state, "audience-card-thinking", false);
            thinking.thinking_origin = "initiative";
            Check(CielAudienceCardState.From(null, thinking, true, false).heading.Contains("自発的"), "initiative is explicit");
            var background = new CielConversation.ActivityState { background_thinking = true, background_for = 3 };
            state = CielAudienceCardState.From(null, background, true, false);
            Check(state.phase == "background", "background thought differs from waiting");
            Render(state, "audience-card-background", false);
            var calling = new CielConversation.ActivityState { calls = new[] { new CielConversation.ActivityCall { label = "ついていく", for_s = 8 } } };
            state = CielAudienceCardState.From(null, calling, true, false);
            Check(state.phase == "calling" && state.elapsed == "8秒経過" && state.current.Contains("返答"), "tool acknowledgement wait is visible");
            Render(state, "audience-card-calling", false);
            calling.tasks = activity.tasks;
            Check(CielAudienceCardState.From(null, calling, true, false).phase == "calling", "pending tool is not masked by another running task");
            calling.calls[0].for_s = 45;
            Check(CielAudienceCardState.From(null, calling, true, false).attention, "long tool wait is distinguished from failure");
            Check(CielAudienceCardState.From(null, idle, true, false, 0, true).phase == "listening", "speech receipt is distinct from idle listening mode");
            Check(CielAudienceCardState.From(null, null, true, false).phase == "unknown", "missing state is not falsely idle");
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
