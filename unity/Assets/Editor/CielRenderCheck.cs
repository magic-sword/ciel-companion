using System.IO;
using Live2D.Cubism.Core;
using Live2D.Cubism.Editor.Importers;
using UnityEditor;
using UnityEngine;

namespace Ciel.EditorTools
{
    /// <summary>
    /// 書き出したシエルのモデルを、パラメーターを変えながら画像に描画して確認する。
    /// 再生モードには入らず、エディタの更新ループ（EditorApplication.update）でモデルを更新して撮影する。
    ///
    /// 使い方（どちらか）：
    ///  1. メニュー CIEL ＞ Render Check（エディタで開いている状態から1クリック）
    ///  2. プロジェクトの .local/render-check/request ファイルを置いてからエディタを起動する
    ///     （起動が落ち着いてから自動で撮影し、終わるとファイルを消して、エディタを終了する）。
    ///     -executeMethod は起動の途中で実行され、その後の更新ループが回らないことがあるため使わない。
    /// 出力: .local/render-check/*.png（Git対象外）
    /// </summary>
    public static class CielRenderCheck
    {
        const string PrefabPath = "Assets/Characters/Ciel/Ciel.prefab";
        const string ModelJsonPath = "Assets/Characters/Ciel/Ciel.model3.json";
        const int Width = 768, Height = 1024;
        const int WaitTicks = 8;   // 値を設定してから撮影するまでの更新回数

        // 名前, ParamAngleX, ParamAngleY, ParamEyeLOpen, ParamEyeROpen
        static readonly (string name, float angleX, float angleY, float eyeL, float eyeR, float mouth)[] Cases =
        {
            ("neutral", 0f, 0f, 1f, 1f, 0f),
            ("angleX_minus30", -30f, 0f, 1f, 1f, 0f),
            ("angleX_plus30", 30f, 0f, 1f, 1f, 0f),
            ("angleX_minus15", -15f, 0f, 1f, 1f, 0f),
            ("angleX_plus15", 15f, 0f, 1f, 1f, 0f),
            ("eyes_half", 0f, 0f, 0.5f, 0.5f, 0f),
            ("eyes_closed", 0f, 0f, 0f, 0f, 0f),
            ("mouth_small", 0f, 0f, 1f, 1f, 0.5f),
            ("mouth_large", 0f, 0f, 1f, 1f, 1f),
            ("pose_xL30_yU30", -30f, 30f, 1f, 1f, 0f),
            ("pose_xL15_yU30", -15f, 30f, 1f, 1f, 0f),
            ("pose_x0_yU30", 0f, 30f, 1f, 1f, 0f),
            ("pose_xR15_yU30", 15f, 30f, 1f, 1f, 0f),
            ("pose_xR30_yU30", 30f, 30f, 1f, 1f, 0f),
            ("pose_xL30_yU15", -30f, 15f, 1f, 1f, 0f),
            ("pose_xL15_yU15", -15f, 15f, 1f, 1f, 0f),
            ("pose_x0_yU15", 0f, 15f, 1f, 1f, 0f),
            ("pose_xR15_yU15", 15f, 15f, 1f, 1f, 0f),
            ("pose_xR30_yU15", 30f, 15f, 1f, 1f, 0f),
            ("pose_xL30_y0", -30f, 0f, 1f, 1f, 0f),
            ("pose_xL15_y0", -15f, 0f, 1f, 1f, 0f),
            ("pose_xR15_y0", 15f, 0f, 1f, 1f, 0f),
            ("pose_xR30_y0", 30f, 0f, 1f, 1f, 0f),
            ("pose_xL30_yD15", -30f, -15f, 1f, 1f, 0f),
            ("pose_xL15_yD15", -15f, -15f, 1f, 1f, 0f),
            ("pose_x0_yD15", 0f, -15f, 1f, 1f, 0f),
            ("pose_xR15_yD15", 15f, -15f, 1f, 1f, 0f),
            ("pose_xR30_yD15", 30f, -15f, 1f, 1f, 0f),
            ("pose_xL30_yD30", -30f, -30f, 1f, 1f, 0f),
            ("pose_xL15_yD30", -15f, -30f, 1f, 1f, 0f),
            ("pose_x0_yD30", 0f, -30f, 1f, 1f, 0f),
            ("pose_xR15_yD30", 15f, -30f, 1f, 1f, 0f),
            ("pose_xR30_yD30", 30f, -30f, 1f, 1f, 0f),
        };

        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/render-check"));
        static string RequestPath => Path.Combine(OutDir, "request");

        static GameObject _instance;
        static CubismModel _model;
        static Camera _cam;
        static RenderTexture _rt;
        static int _caseIndex;
        static int _ticks;
        static bool _exitWhenDone;

        [InitializeOnLoadMethod]
        static void AutoStart()
        {
            if (!File.Exists(RequestPath)) return;
            // 起動が落ち着くまで待ってから始める（delayCall → 更新ループを数十回回す）。
            int waited = 0;
            EditorApplication.CallbackFunction wait = null;
            wait = () =>
            {
                if (++waited < 60) return;
                EditorApplication.update -= wait;
                _exitWhenDone = true;
                File.Delete(RequestPath);
                Begin();
            };
            EditorApplication.update += wait;
        }

        [MenuItem("CIEL/Render Check")]
        static void MenuRun()
        {
            _exitWhenDone = false;
            Begin();
        }

        // moc3 / model3.json を書き出し直しても、起動時にプレハブが再生成されないことがあるので、撮影の前に取り込み直す。
        static void ReimportModel()
        {
            AssetDatabase.ImportAsset(ModelJsonPath, ImportAssetOptions.ForceUpdate);
            var importer = CubismImporter.GetImporterAtPath(ModelJsonPath);
            if (importer == null)
            {
                Debug.LogWarning("CielRenderCheck: no Cubism importer for " + ModelJsonPath);
                return;
            }
            importer.Import();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log("CielRenderCheck: reimported " + ModelJsonPath);
        }

        static void Begin()
        {
            ReimportModel();
            // 取り込み直しの後処理（プレハブ・テクスチャの再生成）が終わるまで、更新ループを回してから置く。
            // すぐに置くと、モデルが描かれず、背景だけの画像になることがあった。
            int waited = 0;
            EditorApplication.CallbackFunction wait = null;
            wait = () =>
            {
                if (++waited < 120) return;
                EditorApplication.update -= wait;
                Place();
            };
            EditorApplication.update += wait;
        }

        static void Place()
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
            if (prefab == null)
            {
                Debug.LogError("CielRenderCheck: prefab not found: " + PrefabPath);
                Finish(2);
                return;
            }

            Directory.CreateDirectory(OutDir);

            _instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            _model = _instance.GetComponent<CubismModel>();
            Debug.Log("CielRenderCheck: drawables=" + _model.Drawables.Length + " parameters=" + _model.Parameters.Length);
            // 各ドローアブルが参照するアトラスの範囲（UV の最小・最大）。どのメッシュに、どの絵が入っているかを確かめる
            Directory.CreateDirectory(OutDir);
            var sb = new System.Text.StringBuilder();
            foreach (var d in _model.Drawables)
            {
                var uv = d.VertexUvs;
                if (uv.Length == 0) continue;
                float x0 = 1, y0 = 1, x1 = 0, y1 = 0;
                foreach (var u in uv) { x0 = Mathf.Min(x0, u.x); y0 = Mathf.Min(y0, u.y); x1 = Mathf.Max(x1, u.x); y1 = Mathf.Max(y1, u.y); }
                sb.AppendLine(d.Id + " " + x0 + " " + x1 + " " + y0 + " " + y1);
            }
            File.WriteAllText(Path.Combine(OutDir, "uvrects.txt"), sb.ToString());

            var camGo = new GameObject("CielRenderCheckCamera");
            _cam = camGo.AddComponent<Camera>();
            _cam.orthographic = true;
            _cam.orthographicSize = 0.75f;
            _cam.transform.position = new Vector3(0f, 0f, -10f);
            _cam.clearFlags = CameraClearFlags.SolidColor;
            _cam.backgroundColor = new Color(0.25f, 0.3f, 0.45f, 1f);
            _rt = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
            _cam.targetTexture = _rt;

            _caseIndex = 0;
            _ticks = 0;
            EditorApplication.update += Tick;
        }

        static void Tick()
        {
            // 同じインスタンスで撮り続けると、1枚目だけ描けて、残りが背景だけになることがあった（原因は未特定。
            // 1枚目は常に描ける）。撮影ごとに、インスタンスを置き直す。
            if (_ticks == 0 || _instance == null || _model == null)
            {
                if (_instance != null) Object.DestroyImmediate(_instance);
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
                _instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                _model = _instance.GetComponent<CubismModel>();
                _ticks = 0;
            }
            var c = Cases[_caseIndex];
            Set("ParamAngleX", c.angleX);
            Set("ParamAngleY", c.angleY);
            Set("ParamEyeLOpen", c.eyeL);
            Set("ParamEyeROpen", c.eyeR);
            Set("ParamMouthOpenY", c.mouth);
            _model.ForceUpdateNow();
            _ticks++;
            if (_ticks < WaitTicks) return;

            _cam.Render();
            var tex = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            RenderTexture.active = _rt;
            tex.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            tex.Apply();
            RenderTexture.active = null;
            var path = Path.Combine(OutDir, c.name + ".png");
            File.WriteAllBytes(path, tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            Debug.Log("CielRenderCheck: wrote " + path + " " + Diagnose());

            _caseIndex++;
            _ticks = 0;
            if (_caseIndex >= Cases.Length)
            {
                EditorApplication.update -= Tick;
                Debug.Log("CIEL_RENDER_CHECK_DONE");
                Finish(0);
            }
        }

        // 描画が空になったときの手掛かり：頂点が NaN のドローアブル数、有効なレンダラー数、パラメータの NaN 数、メッシュの範囲
        static string Diagnose()
        {
            int nanDrawables = 0, enabledRenderers = 0, nanParams = 0;
            var bounds = new Bounds();
            foreach (var d in _model.Drawables)
            {
                var v = d.VertexPositions;
                if (v.Length > 0 && (float.IsNaN(v[0].x) || float.IsNaN(v[0].y))) nanDrawables++;
                var r = d.GetComponent<Live2D.Cubism.Rendering.CubismRenderer>();
                if (r != null && r.MeshRenderer != null && r.MeshRenderer.enabled) enabledRenderers++;
                if (r != null && r.Mesh != null) bounds.Encapsulate(r.Mesh.bounds);
            }
            foreach (var p in _model.Parameters) if (float.IsNaN(p.Value)) nanParams++;
            return "nanDrawables=" + nanDrawables + " renderers=" + enabledRenderers + " nanParams=" + nanParams + " bounds=" + bounds;
        }

        static void Finish(int code)
        {
            if (_instance != null) Object.DestroyImmediate(_instance);
            if (_cam != null) Object.DestroyImmediate(_cam.gameObject);
            if (_rt != null) _rt.Release();
            if (_exitWhenDone) EditorApplication.Exit(code);
        }

        static void Set(string id, float value)
        {
            foreach (var p in _model.Parameters)
            {
                if (p.Id == id)
                {
                    p.Value = Mathf.Clamp(value, p.MinimumValue, p.MaximumValue);
                    return;
                }
            }
        }
    }
}
