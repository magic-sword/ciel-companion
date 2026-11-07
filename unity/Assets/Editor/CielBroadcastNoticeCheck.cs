using System;
using System.IO;
using System.Reflection;
using Ciel.Conversation;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielBroadcastNoticeCheck
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        static int _checks;
        static void Check(bool ok, string name) { if (!ok) throw new Exception("Broadcast notice: " + name); _checks++; }
        static void Set(CielConversation c, string name, object value) => typeof(CielConversation).GetProperty(name).SetValue(c, value);
        static void Invoke(object obj, string method, params object[] args) => obj.GetType().GetMethod(method, Private).Invoke(obj, args);

        public static void Run()
        {
            _checks = 0;
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var c = new GameObject("Notice Check", typeof(CielConversation)).GetComponent<CielConversation>();
            Set(c, "Status", CielConversation.State.Connected);
            Set(c, "GameLabel", "マイクラ"); Set(c, "GameName", "minecraft"); Set(c, "GameListed", true);
            Check(!CielBroadcastNotice.From(c).Visible, "disabled game is not an error");
            Set(c, "GameWanted", true);
            Invoke(c, "SetGameState", false, false, "busy");
            var notice = CielBroadcastNotice.From(c);
            Check(notice.Visible && notice.detail.Contains("別の会話") && notice.action == CielBroadcastNotice.Action.RetryGame, "busy explains cause and recovery");
            c.RetryGameConnection();
            Check(c.GameWanted && !c.GameKnown && c.GameReason == "connecting", "retry keeps game enabled without releasing another session");
            Check(CielBroadcastNotice.From(c, 20).title.Contains("時間がかか"), "missing response becomes a visible long wait");
            Check(CielBroadcastNotice.From(c, 2).action == CielBroadcastNotice.Action.None, "normal connection wait is not an error");
            Invoke(c, "SetGameState", false, false, "unavailable");
            Check(CielBroadcastNotice.From(c).error, "unavailable is shown as error");
            Invoke(c, "SetGameState", false, false, "off");
            Check(CielBroadcastNotice.From(c, 60).title.Contains("切れています"), "explicit disconnect is distinct from slow connection");
            Invoke(c, "SetGameState", true, false, "");
            Check(CielBroadcastNotice.From(c).title.Contains("参加を待"), "body and world readiness are distinct");
            Invoke(c, "SetGameState", true, true, "");
            Check(!CielBroadcastNotice.From(c).Visible, "recovery clears the warning");
            c.RetryGameConnection(); Check(c.GameLinked, "retry does not disturb a healthy link");
            Set(c, "GameName", ""); Check(CielBroadcastNotice.From(c).title.Contains("接続先がありません"), "missing configured game is actionable");
            Set(c, "GameName", "minecraft");
            typeof(CielConversation).GetField("_problem", Private).SetValue(c, "quota");
            Set(c, "ProblemStopped", true); Set(c, "ProblemService", "llm");
            notice = CielBroadcastNotice.From(c);
            Check(notice.error && notice.title.Contains("返事") && notice.detail.Contains("残高") && notice.action == CielBroadcastNotice.Action.Settings,
                "server error includes service and reason rather than suggesting ineffective retry");
            Set(c, "Status", CielConversation.State.Failed);
            Check(CielBroadcastNotice.From(c).action == CielBroadcastNotice.Action.Connect, "failed room connection can retry");
            Set(c, "Status", CielConversation.State.Disconnected);
            Check(!CielBroadcastNotice.From(c).Visible, "intentional disconnection is not alarmed");
            CielAppCompositionCheck.Run();
            RenderBusy();
            Debug.Log("CIEL_BROADCAST_NOTICE_CHECK_OK " + _checks);
        }

        static void RenderBusy()
        {
            EditorSceneManager.OpenScene(CielAppBuildSetup.BroadcastScene);
            var c = UnityEngine.Object.FindAnyObjectByType<CielConversation>();
            Set(c, "Status", CielConversation.State.Connected);
            Set(c, "GameWanted", true); Set(c, "GameListed", true); Set(c, "GameName", "minecraft"); Set(c, "GameLabel", "マイクラ");
            Invoke(c, "SetGameState", false, false, "busy");
            Invoke(UnityEngine.Object.FindAnyObjectByType<CielAppComposition>(), "Awake");
            var ui = UnityEngine.Object.FindAnyObjectByType<CielConversationUI>();
            Invoke(ui, "Awake"); Invoke(ui, "Refresh"); Invoke(ui, "UpdateStatusLine"); Invoke(ui, "UpdateBroadcastMonitor");
            var canvas = ui.transform.Find("ConversationCanvas").GetComponent<Canvas>();
            var panel = canvas.transform.Find("SafeArea/ConnectionNotice");
            Check(panel.gameObject.activeSelf, "warning is visible outside settings");
            Check(canvas.transform.Find("SafeArea/Link/Text").GetComponent<UnityEngine.UI.Text>().text.Contains("ゲームは未接続"), "header distinguishes conversation and game");
            if (SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                var camera = Camera.main;
                var rt = new RenderTexture(1100, 800, 24);
                canvas.renderMode = RenderMode.ScreenSpaceCamera; canvas.worldCamera = camera; canvas.planeDistance = 1;
                camera.targetTexture = rt; camera.aspect = 1.375f;
                Canvas.ForceUpdateCanvases(); camera.Render(); RenderTexture.active = rt;
                var image = new Texture2D(1100, 800, TextureFormat.RGB24, false);
                image.ReadPixels(new Rect(0, 0, 1100, 800), 0, 0); image.Apply();
                var dir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/app-refactor")); Directory.CreateDirectory(dir);
                File.WriteAllBytes(Path.Combine(dir, "broadcast-connection-busy.png"), image.EncodeToPNG());
                RenderTexture.active = null; camera.targetTexture = null;
                UnityEngine.Object.DestroyImmediate(image); rt.Release(); UnityEngine.Object.DestroyImmediate(rt);
            }
            panel.Find("Action").GetComponent<UnityEngine.UI.Button>().onClick.Invoke();
            Check(c.GameWanted && c.GameReason == "connecting", "banner retry button works");
            Invoke(c, "SetGameState", true, true, "");
            ui.GetType().GetField("_broadcastFilledAt", Private).SetValue(ui, -1f);
            Invoke(ui, "UpdateBroadcastMonitor");
            Check(!panel.gameObject.activeSelf, "recovery hides banner");
            Check(((RectTransform)canvas.transform.Find("SafeArea/BroadcastMonitor")).offsetMax.y == -95, "recovery restores monitor space");
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        }
    }
}
