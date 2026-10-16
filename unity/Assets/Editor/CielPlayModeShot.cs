// 会話シーンを実際の再生モードで動かし、ゲームのカメラの映りを数回撮る（会話の接続はしない）。
// 使い方：.local/render-check/playmode-request を置いて、エディタを起動する（-batchmode は付けない）。
// 出力：.local/render-check/playmode-*.png と playmode.txt。終わるとエディタを終了する。
// 要求の文字に "ui" を含めると、代わりに会話の画面を縦長（540×1170）で撮る：
// ui-main.png（ふだん）、ui-settings.png（設定）、ui-volume.png（その場の声の大きさ）。
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
                // 縦長で撮るときは、再生を始める前に Game ビューの大きさを変える（再生中に変えると Live2D が描かれなくなる）
                if (File.ReadAllText(RequestPath).Contains("ui"))
                    SessionState.SetInt(SizeKey, SetGameViewSize(540, 1170));
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
            if (step >= 2 && step < 7 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("ui"))
            {
                if (step < 6) UiShots(step);
                else if (EditorApplication.timeSinceStartup - _mark > 1.0) FinishUiShots();
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

        static double _mark;
        static bool _captured;
        const string SizeKey = "CielPlayModeShot.size";

        // Game ビューを縦長（スマホの大きさ）にして、画面の状態を変えながら撮る。
        // カメラの映りを別の絵（RenderTexture）へ描かせると、Live2D（CubismRenderPassFeature）が描かれないため、Game ビューそのものを撮る
        static void UiShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var ui = Object.FindAnyObjectByType<Ciel.Conversation.CielConversationUI>();
            if (step == 2)
            {
                if (now - _t0 < 1.5 || ui == null) return;
                // "nobg" なら背景を消して撮る（シエルの映りと背景の重なりを切り分ける）
                if (File.ReadAllText(RequestPath).Contains("nobg"))
                    Camera.main.transform.Find("Background")?.gameObject.SetActive(false);
                Next(3);
                return;
            }
            // 撮る（書き出しは次の描画の終わり）→ 0.5 秒待って次の状態へ変える → 1 秒待って次を撮る
            if (!_captured)
            {
                if (now - _mark < 1.0) return;
                var name = step == 3 ? "ui-main" : step == 4 ? "ui-settings" : "ui-volume";
                ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
                _captured = true;
                _mark = now;
                return;
            }
            if (now - _mark < 0.5) return;
            _captured = false;
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            if (step == 3) ui.GetType().GetMethod("OpenSheet", flags).Invoke(ui, new object[] { true });
            if (step == 4)
            {
                ui.GetType().GetMethod("OpenSheet", flags).Invoke(ui, new object[] { false });
                ui.GetType().GetMethod("ShowVolumePop", flags).Invoke(ui, new object[] { true });
            }
            Next(step + 1);
        }

        // 撮り終えたら（撮影は次の描画で書き出されるので、少し待ってから）元の大きさの一覧に戻して終える
        static void FinishUiShots()
        {
            RemoveGameViewSize(SessionState.GetInt(SizeKey, -1));
            SessionState.EraseInt(SizeKey);
            SessionState.SetInt(Key, 7);
            File.Delete(RequestPath);
            EditorApplication.isPlaying = false;
            EditorApplication.delayCall += () => EditorApplication.Exit(0);
        }

        static void Next(int s)
        {
            _mark = EditorApplication.timeSinceStartup;
            SessionState.SetInt(Key, s);
        }

        // ---- Game ビューの大きさ（公開の API がないので、エディタの内部の型を使う） ----

        static object SizeGroup(out System.Type groupType)
        {
            var asm = typeof(EditorWindow).Assembly;
            var sizesType = asm.GetType("UnityEditor.GameViewSizes");
            var instance = typeof(ScriptableSingleton<>).MakeGenericType(sizesType).GetProperty("instance").GetValue(null);
            var current = sizesType.GetProperty("currentGroupType").GetValue(instance);
            var group = sizesType.GetMethod("GetGroup").Invoke(instance, new[] { current });
            groupType = group.GetType();
            return group;
        }

        static int SetGameViewSize(int w, int h)
        {
            var asm = typeof(EditorWindow).Assembly;
            var group = SizeGroup(out var groupType);
            var sizeType = asm.GetType("UnityEditor.GameViewSize");
            var kind = asm.GetType("UnityEditor.GameViewSizeType");
            var size = sizeType.GetConstructor(new[] { kind, typeof(int), typeof(int), typeof(string) })
                .Invoke(new[] { System.Enum.ToObject(kind, 1), w, h, "CielPortrait" });   // 1 = 決まった解像度
            groupType.GetMethod("AddCustomSize").Invoke(group, new[] { size });
            var index = (int)groupType.GetMethod("GetTotalCount").Invoke(group, null) - 1;
            var gvType = asm.GetType("UnityEditor.GameView");
            var gv = EditorWindow.GetWindow(gvType);
            gvType.GetMethod("SizeSelectionCallback", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic)
                .Invoke(gv, new object[] { index, null });
            return index;
        }

        static void RemoveGameViewSize(int index)
        {
            if (index < 0) return;
            var group = SizeGroup(out var groupType);
            var builtin = (int)groupType.GetMethod("GetBuiltinCount").Invoke(group, null);
            groupType.GetMethod("RemoveCustomSize").Invoke(group, new object[] { index - builtin });
        }
    }
}
