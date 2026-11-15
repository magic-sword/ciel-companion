using System;
using System.IO;
using System.Reflection;
using Ciel.Conversation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.EditorTools
{
    // 計画グラフのウィンドウを実際のUnityで組み、絵にして確かめる（.local/app-refactor/plan-graph-*.png）。
    public static class CielPlanWindowCheck
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        static int _checks;
        static void Check(bool ok, string name)
        {
            if (!ok) throw new InvalidOperationException("Plan window: " + name);
            _checks++;
        }

        static CielConversation.GoalState Goal(string planJson) => new CielConversation.GoalState {
            v = 2, type = "goal.state", stream_id = "stream", revision = 1, has_task = true,
            confirmed = true, valid_for_ms = 10000, receivedAt = Time.unscaledTime,
            task = new CielConversation.WorkInfo { session = "server", task_id = "task", revision = 1, title = "Build a dirt shelter.",
                state = "running", can_stop = true, plan = JsonUtility.FromJson<CielConversation.PlanInfo>(planJson) } };

        // The plan the house task showed while it waited for the wool: tools done, a choice waiting, the house still to build.
        const string HousePlan = "{\"v\":1,\"plan_id\":\"plan-1\",\"revision\":12,\"title\":\"dirt_shelter\",\"finished\":false,\"current\":[\"white_bed\"],\"nodes\":["
            + "{\"id\":\"pickaxe\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"wooden_pickaxe ×1\",\"state\":\"done\",\"needs\":[],\"estimate_s\":0},"
            + "{\"id\":\"chest\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"chest\",\"state\":\"done\",\"needs\":[],\"estimate_s\":0},"
            + "{\"id\":\"dirt\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"dirt\",\"state\":\"done\",\"needs\":[],\"estimate_s\":0},"
            + "{\"id\":\"oak_door\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"oak_door\",\"state\":\"done\",\"needs\":[],\"estimate_s\":0},"
            + "{\"id\":\"torch\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"torch\",\"state\":\"done\",\"needs\":[],\"estimate_s\":0},"
            + "{\"id\":\"white_bed\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"white_bed\",\"state\":\"running\",\"needs\":[],\"estimate_s\":160},"
            + "{\"id\":\"white_bed/0\",\"parent\":\"white_bed\",\"kind\":\"make\",\"label\":\"oak_planks ×4\",\"state\":\"done\",\"needs\":[],\"estimate_s\":-1},"
            + "{\"id\":\"white_bed/1\",\"parent\":\"white_bed\",\"kind\":\"decide\",\"label\":\"white_wool ×3\",\"state\":\"waiting_choice\",\"needs\":[\"white_bed/0\"],\"estimate_s\":-1,"
            + "\"choice\":{\"question\":\"how to get 3 white_wool\",\"chosen\":null,\"options\":[{\"id\":\"kill:sheep\",\"summary\":\"about 3 sheep needed\"},{\"id\":\"shear:sheep\",\"summary\":\"a shears to make first\"},{\"id\":\"make\",\"summary\":\"from string\"}]}},"
            + "{\"id\":\"house\",\"parent\":null,\"kind\":\"build\",\"label\":\"house\",\"state\":\"pending\",\"needs\":[\"pickaxe\",\"chest\",\"dirt\",\"oak_door\",\"torch\",\"white_bed\"],\"estimate_s\":131}]}";

        public static void Run()
        {
            _checks = 0;
            var goal = Goal(HousePlan);
            Check(goal.task.plan.Valid && goal.task.plan.nodes.Length == 9, "Unity's parser reads plan v1");
            var view = CielPlanPresentation.From(goal);
            Check(view.visible && view.columns == 2 && view.nodes.Count == 7, "top steps in two columns");
            Check(view.summary.StartsWith("選択待ち"), "the waiting choice is what is shown now");
            var card = CielAudienceCardState.From(goal, null, true, false);
            Check(card.current.StartsWith("選択待ち：white_wool ×3"), "status card shows the plan's step");
            Render(view, "plan-graph-house");
            Debug.Log("CIEL_PLAN_WINDOW_CHECK_OK " + _checks);
        }

        static void Render(CielPlanPresentation view, string name)
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var main = new GameObject("Main Camera", typeof(Camera)); main.tag = "MainCamera";
            var go = new GameObject("Plan Check", typeof(CielPlanWindow));
            var window = go.GetComponent<CielPlanWindow>();
            window.GetType().GetMethod("Awake", Private).Invoke(window, null);
            Check((main.GetComponent<Camera>().cullingMask & (1 << CielPlanWindow.Layer)) == 0, "main camera excludes the plan");
            var camera = go.transform.Find("Plan Source Camera").GetComponent<Camera>();
            Check(camera.cullingMask == 1 << CielPlanWindow.Layer && camera.GetComponent<AudioListener>() == null, "isolated output without audio");
            if (SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                var target = new RenderTexture(1280, 720, 24);
                camera.targetTexture = target; camera.aspect = 1280f / 720;
                Canvas.ForceUpdateCanvases();
                window.Show(view);
                Canvas.ForceUpdateCanvases();
                foreach (var text in go.GetComponentsInChildren<Text>(true)) Check(!text.supportRichText, "plain text prevents markup injection");
                camera.Render();
                RenderTexture.active = target;
                var image = new Texture2D(1280, 720, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0); image.Apply();
                var dir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/app-refactor"));
                Directory.CreateDirectory(dir);
                File.WriteAllBytes(Path.Combine(dir, name + ".png"), image.EncodeToPNG());
                RenderTexture.active = null; camera.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(image); target.Release(); UnityEngine.Object.DestroyImmediate(target);
            }
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }
    }
}
