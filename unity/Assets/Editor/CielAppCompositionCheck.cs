// 接続せずに両方の製品の構成・UI・配信表示の回帰を確認する。
using System;
using System.IO;
using System.Reflection;
using Ciel.Conversation;
using Live2D.Cubism.Framework.MouthMovement;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.EditorTools
{
    public static class CielAppCompositionCheck
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        static int _checks;

        public static void Run()
        {
            _checks = 0;
            CheckScene(CielAppBuildSetup.CompanionScene, false);
            CheckScene(CielAppBuildSetup.BroadcastScene, true);
            CielStreamStatusCheck.Run();
            Debug.Log("CIEL_APP_COMPOSITION_CHECK_OK " + _checks);
        }

        static void Check(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException("App composition: " + message);
            _checks++;
        }

        static void Invoke(object target, string method, params object[] args) =>
            target.GetType().GetMethod(method, Private).Invoke(target, args);

        static void CheckScene(string path, bool broadcast)
        {
            var scene = EditorSceneManager.OpenScene(path);
            var core = UnityEngine.Object.FindObjectsByType<CielConversation>();
            Check(core.Length == 1, "one conversation connection in " + path);
            var c = core[0];
            var root = c.transform.root.gameObject;
            Check(PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(root) == CielAppBuildSetup.RuntimePath, "shared runtime prefab");
            Check(root.GetComponentInChildren<CielConversationUI>(true) == null, "runtime is independent of UI");
            Check(root.GetComponentInChildren<CielStreamWindow>(true) == null, "runtime is independent of output");
            Check(root.GetComponentsInChildren<CubismMouthController>(true).Length == 1, "one shared avatar");
            var serialized = new SerializedObject(c);
            Check(serialized.FindProperty("_mouth").objectReferenceValue != null, "mouth reference preserved");
            Check(serialized.FindProperty("_expression").objectReferenceValue != null, "expression reference preserved");

            var app = UnityEngine.Object.FindAnyObjectByType<CielAppComposition>();
            Check(app != null, "app composition exists");
            Invoke(app, "Awake");   // Edit mode: Start は呼ばず、接続・マイク・外部ウィンドウを始めない
            Check(CielAppComposition.IsBroadcast == broadcast, "correct app profile");
            Check(root.GetComponentInChildren<CielTouch>(true).enabled == !broadcast, "operator clicks do not touch the hidden avatar");
            var touch = new SerializedObject(root.GetComponentInChildren<CielTouch>(true));
            Check(touch.FindProperty("_conversation").objectReferenceValue == c, "touch uses the shared conversation");
            Check(touch.FindProperty("_camera").objectReferenceValue == Camera.main, "touch uses the shared camera");
            Invoke(c, "LoadYouTube");
            if (!broadcast) Check(!c.YouTube, "companion never enables broadcast comments");
            var ui = UnityEngine.Object.FindAnyObjectByType<CielConversationUI>();
            Check(ui != null, "shared UI shell exists");
            Invoke(ui, "Awake");
            var canvas = ui.transform.Find("ConversationCanvas");
            // 配信ページの存在は、階層名で確認（非表示の設定ページも含む）。
            bool hasBroadcastPage = false;
            foreach (var rect in canvas.GetComponentsInChildren<RectTransform>(true))
                hasBroadcastPage |= rect.name == "Page_配信";
            Check(hasBroadcastPage == broadcast, "broadcast settings belong only to broadcast app");
            Check((canvas.Find("BroadcastSurface") != null) == broadcast, "operator screen has an opaque surface");
            Check((canvas.Find("SafeArea/BroadcastMonitor") != null) == broadcast, "operator monitor belongs only to broadcast app");
            Check((ui.GetComponent<CielStreamWindow>() != null) == broadcast, "output belongs only to broadcast app");
            Check(!CielAppComposition.Profile.showStatusOnOutput, "status stays on controls by default");
            Check(canvas.GetComponent<CanvasScaler>().referenceResolution == (broadcast ? new Vector2(960, 720) : new Vector2(390, 844)), "product layout size");
            Invoke(ui, "Refresh");
            Invoke(ui, "UpdateStatusLine");
            if (broadcast) Invoke(ui, "UpdateBroadcastMonitor");
            Render(canvas.GetComponent<Canvas>(), broadcast ? "broadcast-controls" : "companion-controls", broadcast);
            // 生成した UI はシーンを保存せず破棄する。
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }

        static void Render(Canvas canvas, string name, bool broadcast)
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null) return;
            int w = broadcast ? 1100 : 540, h = broadcast ? 800 : 960;
            var camera = Camera.main;
            var rt = new RenderTexture(w, h, 24);
            var previousMode = canvas.renderMode;
            canvas.renderMode = RenderMode.ScreenSpaceCamera;
            canvas.worldCamera = camera;
            canvas.planeDistance = 1;
            camera.targetTexture = rt;
            camera.aspect = (float)w / h;
            Canvas.ForceUpdateCanvases();
            if (broadcast)
            {
                var goal = canvas.transform.Find("SafeArea/BroadcastMonitor/Goal").GetComponent<RectTransform>();
                Check(goal.rect.width > 100 && goal.rect.height > 100, "monitor columns have usable size");
            }
            camera.Render();
            RenderTexture.active = rt;
            var image = new Texture2D(w, h, TextureFormat.RGB24, false);
            image.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            image.Apply();
            var dir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/app-refactor"));
            Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir, name + ".png"), image.EncodeToPNG());
            RenderTexture.active = null;
            camera.targetTexture = null;
            canvas.renderMode = previousMode;
            UnityEngine.Object.DestroyImmediate(image);
            rt.Release();
            UnityEngine.Object.DestroyImmediate(rt);
        }
    }
}
