// 再生中の動き（待機の揺れ・物理演算・目パチ・口）を、再生モードに入らずに編集中に進めて、
// シエルの頂点・パラメーターが壊れない（NaN にならない）か、カメラにどう映るかを確かめる。
// 実行：Unity.exe -batchmode -projectPath unity -executeMethod Ciel.EditorTools.CielPlayCheck.Run -quit -logFile <log>
// 出力：.local/render-check/play-*.png と play.txt
using System.IO;
using System.Text;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using Live2D.Cubism.Framework.Physics;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielPlayCheck
    {
        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/render-check"));

        /// 制御部品を 1 つずつだけ動かして、どれでシエルが消えるかを調べる（映っている画素の数を記録する）
        public static void Bisect()
        {
            var log = new StringBuilder();
            EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
            var names = new System.Collections.Generic.List<string>();
            foreach (var u in Object.FindAnyObjectByType<CubismModel>().GetComponents<ICubismUpdatable>()) names.Add(u.GetType().Name);
            foreach (var only in names)
            {
                EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
                var model = Object.FindAnyObjectByType<CubismModel>();
                var list = new System.Collections.Generic.List<ICubismUpdatable>(model.GetComponents<ICubismUpdatable>());
                list.Sort((a, b) => a.ExecutionOrder.CompareTo(b.ExecutionOrder));
                var firstBad = -1;
                for (int f = 0; f < 40 && firstBad < 0; f++)
                {
                    foreach (var u in list)
                        if (u.GetType().Name != only)
                            try { u.OnLateUpdate(); } catch (System.Exception) { }
                    model.ForceUpdateNow();
                    if (Visible() < 1000) firstBad = f;
                }
                var bad = new StringBuilder();
                foreach (var p in model.Parameters)
                    if (float.IsNaN(p.Value) || Mathf.Abs(p.Value) > 1000) bad.Append($" {p.Id}={p.Value}");
                log.AppendLine($"{only} を除く: 消えたフレーム {firstBad} 異常なパラメーター:{bad}");
            }
            File.WriteAllText(Path.Combine(OutDir, "bisect.txt"), log.ToString());
            Debug.Log("CIEL_BISECT_DONE " + log);
        }

        static int Visible()
        {
            var cam = Camera.main;
            var rt = new RenderTexture(135, 240, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            cam.targetTexture = null;
            RenderTexture.active = null;
            var bg = cam.backgroundColor;
            int n = 0;
            foreach (var c in tex.GetPixels())
                if (Mathf.Abs(c.r - bg.r) + Mathf.Abs(c.g - bg.g) + Mathf.Abs(c.b - bg.b) > 0.1f) n++;
            return n;
        }

        public static void RunSample() => RunScene("Assets/Scenes/SdkCheck.unity");

        public static void Run() => RunScene("Assets/Scenes/Conversation.unity");

        static void RunScene(string scenePath)
        {
            EditorSceneManager.OpenScene(scenePath);
            var model = Object.FindAnyObjectByType<CubismModel>();
            var physics = model.GetComponent<CubismPhysicsController>();
            var updatables = model.GetComponents<ICubismUpdatable>();
            var log = new StringBuilder();
            log.AppendLine("updatables: " + string.Join(", ", System.Array.ConvertAll(updatables, u => u.GetType().Name)));
            if (physics != null)
            {
                physics.Awake();
                physics.Start();
            }
            const float dt = 1f / 30f;
            var rig = physics == null ? null : (CubismPhysicsRig)typeof(CubismPhysicsController)
                .GetProperty("Rig", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance).GetValue(physics);
            for (int frame = 0; frame <= 120; frame++)
            {
                // 頭と体を少し動かして、物理演算に入力を与える
                Set(model, "ParamAngleX", 20f * Mathf.Sin(frame * 0.15f));
                Set(model, "ParamBodyAngleZ", 5f * Mathf.Sin(frame * 0.11f));
                Set(model, "ParamBodyAngleY", -5f * Mathf.Sin(frame * 0.2f));
                // 再生中の CubismUpdateController と同じく、制御部品を実行順に動かす
                var list = new System.Collections.Generic.List<ICubismUpdatable>(updatables);
                list.Sort((a, b) => a.ExecutionOrder.CompareTo(b.ExecutionOrder));
                foreach (var u in list)
                {
                    if (u is CubismPhysicsController) { rig?.Evaluate(dt); continue; }
                    try { u.OnLateUpdate(); }
                    catch (System.Exception e) { if (frame == 0) log.AppendLine($"{u.GetType().Name}: {e.GetType().Name} {e.Message}"); }
                }
                model.ForceUpdateNow();
                if (frame % 40 == 0 || frame == 1) Shot(model, log, frame);
            }
            Directory.CreateDirectory(OutDir);
            File.WriteAllText(Path.Combine(OutDir, "play.txt"), log.ToString());
            Debug.Log("CIEL_PLAY_CHECK_DONE\n" + log);
        }

        static void Set(CubismModel m, string id, float v)
        {
            var p = System.Array.Find(m.Parameters, q => q.Id == id);
            if (p != null) p.Value = v;
        }

        static void Shot(CubismModel model, StringBuilder log, int frame)
        {
            int nanDrawables = 0;
            foreach (var d in model.Drawables)
                foreach (var v in d.VertexPositions)
                    if (float.IsNaN(v.x) || float.IsNaN(v.y)) { nanDrawables++; break; }
            var sb = new StringBuilder();
            foreach (var p in model.Parameters)
            {
                if (float.IsNaN(p.Value) || float.IsInfinity(p.Value)) sb.Append($" {p.Id}=NaN");
                else if (p.Id.StartsWith("ParamHair") || p.Id.StartsWith("ParamBust")) sb.Append($" {p.Id}={p.Value:0.###}");
            }
            int hidden = 0;
            foreach (var d in model.Drawables)
            {
                var r = d.GetComponent<Live2D.Cubism.Rendering.CubismRenderer>();
                if (r == null || r.MeshRenderer == null || !r.MeshRenderer.enabled) hidden++;
            }
            float partOpacity = 0;
            foreach (var p in model.Parts) partOpacity += p.Opacity;
            var rc = model.GetComponent<Live2D.Cubism.Rendering.CubismRenderController>();
            Bounds? bb = null;
            foreach (var r in model.GetComponentsInChildren<MeshRenderer>())
            { if (bb == null) bb = r.bounds; else { var x = bb.Value; x.Encapsulate(r.bounds); bb = x; } }
            var rc0 = model.GetComponent<Live2D.Cubism.Rendering.CubismRenderController>();
            foreach (var r in model.GetComponentsInChildren<MeshRenderer>())
                if (r.name == "Face_Skin" || r.name == "Body")
                {
                    var mf = r.GetComponent<MeshFilter>();
                    var m = mf.sharedMesh;
                    var mpb = new MaterialPropertyBlock();
                    r.GetPropertyBlock(mpb);
                    log.AppendLine($"  {r.name}: shader={r.sharedMaterial?.shader?.name} tex={mpb.GetTexture("_MainTex")?.name} enabled={r.enabled} visible={r.isVisible} order={r.sortingOrder} z={r.transform.position.z} verts={m?.vertexCount} meshBounds={m?.bounds} colors0={(m != null && m.colors.Length > 0 ? m.colors[0].ToString() : "-")} layer={r.gameObject.layer} active={r.gameObject.activeInHierarchy}");
                }
            log.AppendLine($"  bounds={bb} sorting={rc0.SortingMode} depthOffset={rc0.DepthOffset} modelPos={model.transform.position} scale={model.transform.lossyScale} cam={Camera.main.transform.position}");
            log.AppendLine($"frame={frame} renderOpacity={rc.Opacity} nanDrawables={nanDrawables} hiddenRenderers={hidden}/{model.Drawables.Length} partOpacitySum={partOpacity:0.##}/{model.Parts.Length} |{sb}");

            var cam = Camera.main;
            var rt = new RenderTexture(270, 480, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            File.WriteAllBytes(Path.Combine(OutDir, $"play-{frame}.png"), tex.EncodeToPNG());
            cam.targetTexture = null;
            RenderTexture.active = null;
        }
    }
}
