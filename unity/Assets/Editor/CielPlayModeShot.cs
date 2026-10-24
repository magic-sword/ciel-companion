// 会話シーンを実際の再生モードで動かし、ゲームのカメラの映りを数回撮る（会話の接続はしない）。
// 使い方：.local/render-check/playmode-request を置いて、エディタを起動する（-batchmode は付けない）。
// 出力：.local/render-check/playmode-*.png と playmode.txt。終わるとエディタを終了する。
// 要求の文字に "ui" を含めると、代わりに会話の画面を縦長（540×1170）で撮る：
// ui-main.png（ふだん）、ui-settings.png・ui-settings-bg.png・ui-settings-other.png（設定のタブ）、ui-volume.png（その場の声の大きさ）。
// 設定画面の中を押しても閉じないかを、押す操作を真似して確かめ、ui.txt に書く。
// "touch" を含めると、縦長の画面でシエルに触れる操作を再現し、触れた点の表示（CielTouchVisual）を撮る：
// touch-converge.png（触れ始め）、touch-hold.png（長く触れる）、touch-stroke-start.png（撫で始め）、touch-stroke.png（頭を撫で続ける）、touch-tap.png（ほっぺをつつく）、touch-none.png（反応しない胸）。
// "people" を含めると、合成の名簿（speakers.state）を流し込み、参加者の札とパネルを縦長で撮る：
// people-row.png（札の列。最後に話した人が光る）、people-remembered.png（声を覚えている人）、people-unknown.png（名前を知らない人）、
// people-duplicate.png（ほかの人と同じ名前を入れたときの注意）。パネルの部品の数を people.txt に書く。
// "summary" を含めると、合成のまとめ（ciel.summary）を流し込み、まとめの帯とパネルを縦長で撮る：
// summary-strip.png（記録中の帯）、summary-panel.png（帯をタップして開いたパネル）、summary-glow.png（項目が増えて光る）、
// summary-closed.png（帯をもう一度タップして閉じたあと）、
// summary-done.png（終えたあと：送った結果と、種類を選ぶボタン）。パネルの部品の数を summary.txt に書く。
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
                var request = File.ReadAllText(RequestPath);
                if (request.Contains("ui") || request.Contains("resize") || request.Contains("touch") || request.Contains("cheek")
                    || request.Contains("people") || request.Contains("summary") || request.Contains("status"))
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
            if (step >= 2 && step < 8 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("speakerswitch"))
            {
                SpeakerSwitch(step);
                return;
            }
            if (step >= 2 && step < 8 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("resize"))
            {
                ResizeShots(step);
                return;
            }
            if (step >= 2 && step < 8 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("cheek"))
            {
                CheekShots(step);
                return;
            }
            if (step >= 2 && step < 8 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("touch"))
            {
                TouchShots(step);
                return;
            }
            if (step >= 2 && step < 9 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("status"))
            {
                StatusShots(step);
                return;
            }
            if (step >= 2 && step < 9 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("summary"))
            {
                SummaryShots(step);
                return;
            }
            if (step >= 2 && step < 8 && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("people"))
            {
                PeopleShots(step);
                return;
            }
            if (step >= 2 && step < Done && EditorApplication.isPlaying && File.ReadAllText(RequestPath).Contains("ui"))
            {
                if (step < 8) UiShots(step);
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
        const int Done = 99;   // 撮り終えた段（どの撮り方の分岐にも当たらない）
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
                // "bg:名前" なら、その背景で撮る（例：bg:salon_night）
                var bg = System.Text.RegularExpressions.Regex.Match(File.ReadAllText(RequestPath), @"bg:(\w+)");
                if (bg.Success) Object.FindAnyObjectByType<Ciel.Conversation.CielBackground>()?.Set(bg.Groups[1].Value);
                Next(3);
                return;
            }
            // 撮る（書き出しは次の描画の終わり）→ 0.5 秒待って次の状態へ変える → 1 秒待って次を撮る
            if (!_captured)
            {
                if (now - _mark < 1.0) return;
                var name = new[] { "ui-main", "ui-settings", "ui-settings-bg", "ui-settings-other", "ui-volume" }[step - 3];
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
                // 設定画面の中（何もない所）を押したことにして、閉じないかを確かめる
                var sheet = ui.transform.Find("ConversationCanvas/Settings/Sheet");
                var es = UnityEngine.EventSystems.EventSystem.current;
                UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(sheet.gameObject,
                    new UnityEngine.EventSystems.PointerEventData(es), UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
                var open = (bool)ui.GetType().GetField("_sheetOpen", flags).GetValue(ui);
                File.AppendAllText(Path.Combine(OutDir, "ui.txt"), $"設定の中を押したあと：{(open ? "開いたまま" : "閉じた")}\n");
                ui.GetType().GetMethod("ShowPage", flags).Invoke(ui, new object[] { 1 });
            }
            if (step == 5) ui.GetType().GetMethod("ShowPage", flags).Invoke(ui, new object[] { 2 });
            if (step == 6)
            {
                ui.GetType().GetMethod("OpenSheet", flags).Invoke(ui, new object[] { false });
                ui.GetType().GetMethod("ShowVolumePop", flags).Invoke(ui, new object[] { true });
            }
            Next(step + 1);
        }

        // 再生中に Game ビューの大きさを変えても、シエルが描かれ続けるかを確かめる。
        // resize-0.png（縦長）→ 横長へ変える → resize-1.png（1 秒後）→ "fix:…" があれば試す → resize-2.png（1.5 秒後）
        // 撮影は次の描画で書き出されるので、撮る段と大きさ・状態を変える段を分ける
        static void ResizeShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            if (step == 2) { if (now - _t0 < 2.0) return; Shot("resize-0"); Next(3); return; }
            if (step == 3) { if (now - _mark < 0.5) return; SessionState.SetInt(SizeKey + ".2", SetGameViewSize(1110, 620)); Next(4); return; }
            if (step == 4) { if (now - _mark < 1.0) return; Shot("resize-1"); Next(5); return; }
            if (step == 5)
            {
                if (now - _mark < 0.5) return;
                // 試し："fix:release" は Live2D の作業用の絵を全部手放す、"fix:toggle" は描画の部品を止めて動かし直す
                var req = File.ReadAllText(RequestPath);
                if (req.Contains("fix:release")) Live2D.Cubism.Rendering.CubismOffscreenRenderTextureManager.GetInstance().Release();
                if (req.Contains("fix:toggle"))
                    foreach (var rc in Object.FindObjectsByType<Live2D.Cubism.Rendering.CubismRenderController>())
                    {
                        rc.enabled = false;
                        var c = rc;
                        EditorApplication.delayCall += () => c.enabled = true;
                    }
                Next(6);
                return;
            }
            if (step == 6) { if (now - _mark < 1.5) return; Shot("resize-2"); Next(7); return; }
            if (now - _mark < 1.0) return;
            RemoveGameViewSize(SessionState.GetInt(SizeKey + ".2", -1));
            FinishUiShots();

            static void Shot(string name)
            {
                ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
                File.AppendAllText(Path.Combine(OutDir, "resize.txt"),
                    $"{name} t={EditorApplication.timeSinceStartup - _t0:0.0} screen={Screen.width}x{Screen.height} frame={Time.frameCount}\n");
            }
        }

        // 触れる操作を時間の順に再現して撮る（CielTouchCheck と同じく、CielTouch の Press・Drag・Release を直接呼ぶ）
        static readonly (float t, string action)[] TouchScript =
        {
            (0.00f, "press:head"), (0.10f, "shot:touch-converge"), (0.75f, "shot:touch-hold"),
            (1.00f, "stroke"), (1.30f, "shot:touch-stroke-start"), (2.30f, "shot:touch-stroke"), (2.60f, "release"),
            (3.40f, "press:face"), (3.48f, "release"), (3.60f, "shot:touch-tap"),
            (4.40f, "press:none"), (4.50f, "shot:touch-none"), (4.60f, "release"),
        };
        static int _touchIndex;
        static Vector2 _touchPoint;
        static readonly System.Collections.Generic.Dictionary<string, Vector2> TouchPoints = new System.Collections.Generic.Dictionary<string, Vector2>();

        static void TouchShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var touch = Object.FindAnyObjectByType<Ciel.Conversation.CielTouch>();
            if (step == 2)
            {
                if (now - _t0 < 2.0 || touch == null) return;
                // 各部位として判定される点：画面を 8 画素おきに調べ、その部位の点の中央に近い点
                var found = new System.Collections.Generic.Dictionary<Ciel.Conversation.CielTouch.Part, System.Collections.Generic.List<Vector2>>();
                for (int y = 0; y < Screen.height; y += 8)
                    for (int x = 0; x < Screen.width; x += 8)
                    {
                        var part = touch.PartAt(new Vector2(x, y));
                        if (!found.TryGetValue(part, out var list)) found[part] = list = new System.Collections.Generic.List<Vector2>();
                        list.Add(new Vector2(x, y));
                    }
                Vector2 Middle(Ciel.Conversation.CielTouch.Part part)
                {
                    var list = found[part];
                    var mean = Vector2.zero;
                    foreach (var p in list) mean += p;
                    mean /= list.Count;
                    var best = list[0];
                    foreach (var p in list) if ((p - mean).sqrMagnitude < (best - mean).sqrMagnitude) best = p;
                    return best;
                }
                TouchPoints["head"] = Middle(Ciel.Conversation.CielTouch.Part.Head);
                TouchPoints["face"] = Middle(Ciel.Conversation.CielTouch.Part.Face);
                // 反応しない点は、シエルの胸（頭の真下で、髪や首から離れたところ）で探す
                var head = TouchPoints["head"];
                var none = head;
                for (float y = head.y - Screen.height * 0.3f; y > Screen.height * 0.2f; y -= 8)
                {
                    none = new Vector2(head.x, y);
                    if (touch.PartAt(none) == Ciel.Conversation.CielTouch.Part.None && touch.DescribeAt(none).Contains("Body48")) break;
                }
                TouchPoints["none"] = none;
                File.AppendAllText(Path.Combine(OutDir, "touch.txt"), $"screen={Screen.width}x{Screen.height} head={TouchPoints["head"]} face={TouchPoints["face"]} none={none} {touch.DescribeAt(none)}\n");
                _touchIndex = 0;
                Next(3);
                return;
            }
            var t = (float)(now - _mark);
            // なぞる：頭の上を左右に往復する（画面の高さの約 6%）
            if (step == 4) touch.Drag(_touchPoint + new Vector2(Mathf.Sin((t - 1.0f) * 9f) * Screen.height * 0.03f, 0));
            while (_touchIndex < TouchScript.Length && t >= TouchScript[_touchIndex].t)
            {
                var a = TouchScript[_touchIndex++].action;
                if (a.StartsWith("press:"))
                {
                    _touchPoint = TouchPoints[a.Substring(6)];
                    touch.Press(_touchPoint);
                    File.AppendAllText(Path.Combine(OutDir, "touch.txt"), $"{a} part={touch.PartAt(_touchPoint)}\n");
                }
                else if (a == "stroke") SessionState.SetInt(Key, 4);
                else if (a == "release") { touch.Release(); SessionState.SetInt(Key, 3); }
                else if (a.StartsWith("shot:"))
                {
                    ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, a.Substring(5) + ".png"));
                    File.AppendAllText(Path.Combine(OutDir, "touch.txt"), $"{a.Substring(5)} t={t:0.00} last={touch.LastTouch} stroke={touch.StrokeAmount:0.00}\n");
                }
            }
            if (_touchIndex >= TouchScript.Length && t > 5.5f) FinishUiShots();
        }

        // "cheek"：画面の右（モデルの左）のほっぺを、つつく → 離す（ぷるん）→ やさしく引く → 強く引く → 離す、の順に撮る。
        // cheek-*.png と、各コマのパラメーターを cheek.txt に書く
        static readonly (float t, string action)[] CheekScript =
        {
            (0.00f, "press"), (0.12f, "shot:cheek-poke"), (0.50f, "release"),
            (0.53f, "shot:cheek-release-1"), (0.60f, "shot:cheek-release-2"), (0.70f, "shot:cheek-release-3"), (0.85f, "shot:cheek-release-4"),
            (1.50f, "press"), (1.50f, "pull-gentle"), (2.40f, "shot:cheek-pull-gentle"),
            (2.50f, "pull-hard"), (2.90f, "shot:cheek-pull-hard"), (3.00f, "release"),
            (3.05f, "shot:cheek-pull-back-1"), (3.15f, "shot:cheek-pull-back-2"), (3.40f, "shot:cheek-pull-back-3"),
        };
        static string _cheekMode = "";

        static void CheekShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var touch = Object.FindAnyObjectByType<Ciel.Conversation.CielTouch>();
            var log = Path.Combine(OutDir, "cheek.txt");
            if (step == 2)
            {
                if (now - _t0 < 2.0 || touch == null) return;
                // L のほっぺとみなされる点の真ん中
                var sum = Vector2.zero;
                var n = 0;
                for (int y = 0; y < Screen.height; y += 6)
                    for (int x = 0; x < Screen.width; x += 6)
                    {
                        var p = new Vector2(x, y);
                        if (touch.PartAt(p) == Ciel.Conversation.CielTouch.Part.Face && touch.CheekAt(p) == 1) { sum += p; n++; }
                    }
                if (n == 0) { File.AppendAllText(log, "no cheek point\n"); FinishUiShots(); return; }
                _touchPoint = sum / n;
                File.AppendAllText(log, $"screen={Screen.width}x{Screen.height} cheekL={_touchPoint} points={n}\n");
                _touchIndex = 0;
                _cheekMode = "";
                Next(3);
                return;
            }
            var t = (float)(now - _mark);
            // 引っ張る：やさしく（0.9 秒かけて外・下へ画面の高さの 3%）、強く（0.3 秒で 9% へ）
            var h = Screen.height;
            if (_cheekMode == "pull-gentle")
                touch.Drag(_touchPoint + new Vector2(0.03f, -0.015f) * h * Mathf.Clamp01((t - 1.5f) / 0.9f));
            else if (_cheekMode == "pull-hard")
                touch.Drag(_touchPoint + Vector2.Lerp(new Vector2(0.03f, -0.015f), new Vector2(0.09f, -0.04f), Mathf.Clamp01((t - 2.5f) / 0.3f)) * h);
            while (_touchIndex < CheekScript.Length && t >= CheekScript[_touchIndex].t)
            {
                var a = CheekScript[_touchIndex++].action;
                if (a == "press") { touch.Press(_touchPoint); File.AppendAllText(log, $"press part={touch.PartAt(_touchPoint)} cheek={touch.CheekAt(_touchPoint)}\n"); }
                else if (a == "release") { _cheekMode = ""; touch.Release(); }
                else if (a.StartsWith("pull-")) _cheekMode = a;
                else if (a.StartsWith("shot:"))
                {
                    ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, a.Substring(5) + ".png"));
                    var model = touch.GetComponent<Live2D.Cubism.Core.CubismModel>();
                    var sb = new System.Text.StringBuilder($"{a.Substring(5)} t={t:0.00} last={touch.LastTouch}");
                    foreach (var id in new[] { "ParamCielCheekPokeL", "ParamCielCheekJiggleL", "ParamCielCheekPullXL", "ParamCielCheekPullYL", "ParamCheek", "ParamEyeLOpen" })
                        foreach (var p in model.Parameters) if (p.Id == id) sb.Append($" {id}={p.Value:0.00}");
                    var expression = touch.GetComponent<Ciel.Conversation.CielExpression>();
                    if (expression != null) sb.Append($" expression={expression.Current}");
                    File.AppendAllText(log, sb + "\n");
                }
            }
            if (_touchIndex >= CheekScript.Length && t > 4.5f) FinishUiShots();
        }

        // "speakerswitch connect"：会話につなぎ、シエルの声が流れているあいだに、声の出力を別の機器 → 既定へ切り替える。
        // 結果はエディタのログ（[CielConversation] の行）で見る。PC のスピーカーからシエルの声が出る
        static void SpeakerSwitch(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var c = Object.FindAnyObjectByType<Ciel.Conversation.CielConversation>();
            var voice = c != null && c.GetType().GetField("_voiceStream", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic).GetValue(c) != null;
            if (step == 2) { if (!voice && now - _t0 < 30) return; Next(3); return; }
            if (step == 3)
            {
                if (now - _mark < 1.0) return;
                var other = c.SpeakerDevices.Find(d => d.guid != Ciel.Conversation.WindowsDefaultAudio.Speaker() && !d.name.Contains("CABLE") && !d.name.Contains("Cable"));   // いまの既定と違う機器
                if (other.guid == null && c.SpeakerDevices.Count > 0) other = c.SpeakerDevices[0];
                Debug.Log($"[SpeakerSwitch] 声の受信中={voice}、'{other.name}' へ切り替える");
                c.SelectSpeaker(other.guid);
                Next(4);
                return;
            }
            if (step == 4) { if (now - _mark < 4.0) return; Debug.Log("[SpeakerSwitch] 既定へ切り替える"); c.SelectSpeaker(null); Next(5); return; }
            if (step == 5) { if (now - _mark < 4.0) return; Next(6); return; }
            if (now - _mark < 0.5) return;
            FinishUiShots();
        }

        // 参加者の札とパネル。会話サーバーにはつながず、合成の名簿を CielConversation に渡す
        static void PeopleShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var ui = Object.FindAnyObjectByType<Ciel.Conversation.CielConversationUI>();
            var c = Object.FindAnyObjectByType<Ciel.Conversation.CielConversation>();
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            var log = Path.Combine(OutDir, "people.txt");
            if (step == 2)
            {
                if (now - _t0 < 1.5 || ui == null || c == null) return;
                File.WriteAllText(log, "");
                typeof(Ciel.Conversation.CielConversation).GetProperty("Status").GetSetMethod(true)
                    .Invoke(c, new object[] { Ciel.Conversation.CielConversation.State.Connected });
                const string json = "{\"v\":1,\"type\":\"speakers.state\",\"speakers\":["
                    + "{\"id\":\"p1\",\"name\":\"ハカセ\",\"named\":true,\"remembered\":true},"
                    + "{\"id\":\"p2\",\"name\":\"ミナ\",\"named\":true,\"remembered\":false},"
                    + "{\"id\":\"p3\",\"name\":\"知らない人A\",\"named\":false,\"remembered\":false},"
                    + "{\"id\":\"p4\",\"name\":\"知らない人B\",\"named\":false,\"remembered\":false}],"
                    + "\"speaking\":\"p1\",\"speaking_sure\":true,\"heard\":1,\"correctable\":\"p1\"}";
                typeof(Ciel.Conversation.CielConversation).GetMethod("OnSpeakers", flags)
                    .Invoke(c, new object[] { System.Text.Encoding.UTF8.GetBytes(json) });
                Next(3);
                return;
            }
            if (!_captured)
            {
                if (now - _mark < 1.0) return;
                var name = new[] { "people-row", "people-remembered", "people-unknown", "people-duplicate" }[step - 3];
                ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
                var panel = ui.transform.Find("ConversationCanvas/SafeArea/PeoplePanel");
                var buttons = panel.GetComponentsInChildren<UnityEngine.UI.Button>().Length;
                var inputs = panel.GetComponentsInChildren<UnityEngine.UI.InputField>().Length;
                var chips = ui.transform.Find("ConversationCanvas/SafeArea/People/Chips").childCount;
                File.AppendAllText(log, $"{name}: 札 {chips - 1}、パネル {(panel.gameObject.activeSelf ? "開" : "閉")}、ボタン {buttons}、入力 {inputs}\n");
                _captured = true;
                _mark = now;
                return;
            }
            if (now - _mark < 0.5) return;
            _captured = false;
            var show = ui.GetType().GetMethod("ShowPerson", flags);
            if (step == 3) show.Invoke(ui, new object[] { "p1" });
            if (step == 4) show.Invoke(ui, new object[] { "p3" });
            if (step == 5)
            {
                // ミナさんと同じ名前を入れて「決める」：送らずに注意を出す
                var panel = ui.transform.Find("ConversationCanvas/SafeArea/PeoplePanel");
                panel.GetComponentInChildren<UnityEngine.UI.InputField>().text = "ミナさん";
                panel.Find("Viewport/Content/Row/Set").GetComponent<UnityEngine.UI.Button>().onClick.Invoke();
            }
            if (step == 6) { FinishUiShots(); return; }
            Next(step + 1);
        }

        [System.Serializable]
        class SummaryPart
        {
            public string text;
            public int seq, part, parts;
        }

        static int _summarySeq;

        // 会話サーバーの minutes.py と同じ形のまとめを、CielConversation に渡す
        static void SendSummary(Ciel.Conversation.CielConversation c, bool recording, string stage, bool extra, bool updating = false)
        {
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            string Item(string id, int rev, string text, string who = "", string due = "", string points = "") =>
                $"{{\"id\":\"{id}\",\"rev\":{rev},\"text\":\"{text}\",\"points\":[{points}],\"who\":\"{who}\",\"due\":\"{due}\",\"done\":false,\"status\":\"\",\"sources\":[]}}";
            var decisions = Item("decisions-2", 1, "展示のテーマは「冬の星空」にする")
                + (extra ? "," + Item("decisions-5", 2, "予算は三万円までにする") : "");
            var state = "{\"v\":1,\"type\":\"summary.state\",\"meeting_id\":\"m1\",\"recording\":" + (recording ? "true" : "false")
                + $",\"stage\":\"{stage}\",\"template\":\"meeting\",\"label\":\"会議の議事録\",\"title\":\"来月の展示の準備\","
                + "\"summary\":\"" + (recording ? "" : "展示のテーマと予算、準備の分担を決めた。") + "\","
                + "\"current_topic\":\"" + (extra ? "予算と見積もり、それから会場への問い合わせの分担について" : "展示のテーマ") + "\",\"attendees\":[],"
                + $"\"started_at\":{System.DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 900},\"updated_at\":{System.DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 40},"
                + $"\"pending_turns\":{(extra ? 0 : 3)},\"updating\":{(updating ? "true" : "false")},\"rev\":{(extra ? 2 : 1)},\"sections\":["
                + "{\"id\":\"topics\",\"label\":\"話したこと\",\"kind\":\"topic\",\"items\":["
                + Item("topics-1", 1, "展示のテーマ", points: "\"星空の写真を中心にする\",\"子ども向けの解説も置く\"") + "]},"
                + "{\"id\":\"decisions\",\"label\":\"決まったこと\",\"kind\":\"decision\",\"items\":[" + decisions + "]},"
                + "{\"id\":\"actions\",\"label\":\"宿題\",\"kind\":\"action\",\"items\":["
                + Item("actions-3", 1, "会場に写真の大きさを問い合わせる", "ミナ", "10/30") + "]},"
                + "{\"id\":\"questions\",\"label\":\"決まっていないこと\",\"kind\":\"question\",\"items\":["
                + Item("questions-4", 1, "解説を印刷するか、画面で見せるか") + "]}]}";
            var part = JsonUtility.ToJson(new SummaryPart { text = state, seq = ++_summarySeq, part = 0, parts = 1 });
            typeof(Ciel.Conversation.CielConversation).GetMethod("OnSummaryPart", flags)
                .Invoke(c, new object[] { System.Text.Encoding.UTF8.GetBytes(part) });
        }

        static void SummaryShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var ui = Object.FindAnyObjectByType<Ciel.Conversation.CielConversationUI>();
            var c = Object.FindAnyObjectByType<Ciel.Conversation.CielConversation>();
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            var log = Path.Combine(OutDir, "summary.txt");
            if (step == 2)
            {
                if (now - _t0 < 1.5 || ui == null || c == null) return;
                File.WriteAllText(log, "");
                typeof(Ciel.Conversation.CielConversation).GetProperty("Status").GetSetMethod(true)
                    .Invoke(c, new object[] { Ciel.Conversation.CielConversation.State.Connected });
                const string people = "{\"v\":1,\"type\":\"speakers.state\",\"speakers\":["
                    + "{\"id\":\"p1\",\"name\":\"ハカセ\",\"named\":true,\"remembered\":true},"
                    + "{\"id\":\"p2\",\"name\":\"ミナ\",\"named\":true,\"remembered\":false}],"
                    + "\"speaking\":\"p2\",\"speaking_sure\":true,\"heard\":1,\"correctable\":\"\"}";
                typeof(Ciel.Conversation.CielConversation).GetMethod("OnSpeakers", flags)
                    .Invoke(c, new object[] { System.Text.Encoding.UTF8.GetBytes(people) });
                SendSummary(c, true, "recording", false);
                // 調べものをしたあと（右上に「調査・出典」のボタンが出ている。帯の文言が消えた条件。2026-10-23、Android）
                ((UnityEngine.UI.Button)ui.GetType().GetField("_researchButton", flags).GetValue(ui)).gameObject.SetActive(true);
                Next(3);
                return;
            }
            if (!_captured)
            {
                if (now - _mark < 1.0) return;
                var name = new[] { "summary-strip", "summary-panel", "summary-glow", "summary-closed", "summary-done" }[step - 3];
                ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
                var panel = ui.transform.Find("ConversationCanvas/SafeArea/SummaryPanel");
                var items = panel.Find("Viewport/Content").GetComponentsInChildren<UnityEngine.UI.VerticalLayoutGroup>(true).Length - 1;
                var strip = ui.transform.Find("ConversationCanvas/SafeArea/SummaryStrip").gameObject.activeSelf;
                File.AppendAllText(log, $"{name}: 帯 {(strip ? "出" : "無")}、パネル {(panel.gameObject.activeSelf ? "開" : "閉")}、項目 {items}、"
                    + $"ボタン {panel.GetComponentsInChildren<UnityEngine.UI.Button>().Length}\n");
                _captured = true;
                _mark = now;
                return;
            }
            if (now - _mark < 0.5) return;
            _captured = false;
            // 帯をタップして開き、もう一度タップして閉じる（利用者の操作と同じ。閉じたあとの帯も撮る）
            var stripButton = ui.transform.Find("ConversationCanvas/SafeArea/SummaryStrip").GetComponent<UnityEngine.UI.Button>();
            if (step == 3) stripButton.onClick.Invoke();
            if (step == 4) SendSummary(c, true, "recording", true);
            if (step == 5) stripButton.onClick.Invoke();
            if (step == 6)
            {
                SendSummary(c, false, "sent", true);
                ui.GetType().GetMethod("ShowSummary", flags).Invoke(ui, new object[] { true });
            }
            if (step == 7) { FinishUiShots(); return; }
            Next(step + 1);
        }

        // シエルの状態の表示（マイクの上）と、裏で進んでいること（声の様子の上）。会話サーバーにはつながず、状態を直接入れる
        static void StatusShots(int step)
        {
            var now = EditorApplication.timeSinceStartup;
            var ui = Object.FindAnyObjectByType<Ciel.Conversation.CielConversationUI>();
            var c = Object.FindAnyObjectByType<Ciel.Conversation.CielConversation>();
            var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
            var type = typeof(Ciel.Conversation.CielConversation);
            void Set(string field, object value) => type.GetField(field, flags).SetValue(c, value);
            var log = Path.Combine(OutDir, "status.txt");
            if (step == 2)
            {
                if (now - _t0 < 1.5 || ui == null || c == null) return;
                File.WriteAllText(log, "");
                type.GetProperty("Status").GetSetMethod(true).Invoke(c, new object[] { Ciel.Conversation.CielConversation.State.Connected });
                Set("_recording", true);
                Set("_userSpeaking", true);   // 聞いています
                Next(3);
                return;
            }
            if (!_captured)
            {
                if (now - _mark < 1.0) return;
                var name = new[] { "status-listening", "status-thinking", "status-research", "status-speaking" }[step - 3];
                ScreenCapture.CaptureScreenshot(Path.Combine(OutDir, name + ".png"));
                string Text(string path) => ui.transform.Find("ConversationCanvas/SafeArea/" + path).GetComponent<UnityEngine.UI.Text>().text;
                var tasks = string.Join("・", System.Linq.Enumerable.Select(
                    ui.transform.Find("ConversationCanvas/SafeArea/Tasks").GetComponentsInChildren<UnityEngine.UI.Text>(), t => t.text));
                File.AppendAllText(log, $"{name}: {Text("Status")}｜札 {tasks}｜{Text("Caption")}\n");
                _captured = true;
                _mark = now;
                return;
            }
            if (now - _mark < 0.5) return;
            _captured = false;
            if (step == 3)
            {
                // 聞き終えて返事を考えている。議事録のライブの更新も走っている
                Set("_userSpeaking", false);
                Set("_thinkingSince", Time.unscaledTime);
                SendSummary(c, true, "recording", false, updating: true);
            }
            if (step == 4)
            {
                // Web で調べている（調べた記録が pending）
                const string pending = "{\"v\":1,\"type\":\"research.result\",\"id\":1,\"question\":\"PHPの脆弱性\",\"checked_at\":null,"
                    + "\"status\":\"pending\",\"clipped\":false,\"part_count\":0}";
                type.GetMethod("OnResearchData", flags).Invoke(c, new object[] { System.Text.Encoding.UTF8.GetBytes(pending) });
            }
            if (step == 5) type.GetProperty("AgentState").GetSetMethod(true).Invoke(c, new object[] { "speaking" });   // 調べながら話している
            if (step == 6) { FinishUiShots(); return; }
            Next(step + 1);
        }

        // 撮り終えたら（撮影は次の描画で書き出されるので、少し待ってから）元の大きさの一覧に戻して終える
        static void FinishUiShots()
        {
            RemoveGameViewSize(SessionState.GetInt(SizeKey, -1));
            SessionState.EraseInt(SizeKey);
            SessionState.SetInt(Key, 8);
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
