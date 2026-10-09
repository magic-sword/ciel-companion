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
            var c = Cases[_caseIndex];
            Set("ParamAngleX", c.angleX);
            Set("ParamAngleY", c.angleY);
            Set("ParamEyeLOpen", c.eyeL);
            Set("ParamEyeROpen", c.eyeR);
            Set("ParamMouthOpenY", c.mouth);
            _model.ForceUpdateNow();
            _ticks++;
            if (_ticks < WaitTicks) return;

            if (c.name.StartsWith("hide_"))
            {
                var hide = c.name.Substring(5).Split('+');
                foreach (var d in _model.Drawables)
                    foreach (var h in hide)
                        if (d.name == h) d.GetComponent<MeshRenderer>().enabled = false;
            }
            if (c.name == "only_Face_Skin")
                foreach (var dd in _model.Drawables)
                    if (dd.name == "Face_Skin" || dd.name.StartsWith("Mouth"))
                    {
                        var mf = dd.GetComponent<MeshFilter>().sharedMesh;
                        Debug.Log("CielRenderCheck: DIAG " + dd.name + " bounds=" + mf.bounds + " verts=" + mf.vertexCount + " uv0=" + mf.uv[0] + " idx=" + dd.GetComponent<MeshRenderer>().enabled + " sorting=" + dd.GetComponent<MeshRenderer>().sortingOrder);
                    }
            if (c.name == "neutral")
                foreach (var dd in _model.Drawables)
                {
                    var uvs = dd.GetComponent<MeshFilter>().sharedMesh.uv;
                    float u0 = 9, u1 = -9, v0 = 9, v1 = -9;
                    foreach (var uv in uvs) { u0 = Mathf.Min(u0, uv.x); u1 = Mathf.Max(u1, uv.x); v0 = Mathf.Min(v0, uv.y); v1 = Mathf.Max(v1, uv.y); }
                    Debug.Log("CielRenderCheck: UVRECT " + dd.name + " " + u0 + " " + u1 + " " + v0 + " " + v1);
                }
            if (c.name.StartsWith("only_Face_Base"))
                foreach (var dd in _model.Drawables)
                    if (dd.name == "Face_Base")
                    {
                        var mf = dd.GetComponent<MeshFilter>().sharedMesh;
                        var rr = dd.GetComponent<Live2D.Cubism.Rendering.CubismRenderer>();
                        Debug.Log("CielRenderCheck: FB " + c.name + " bounds=" + mf.bounds + " verts=" + mf.vertexCount + " tris=" + (mf.triangles.Length / 3) + " color=" + rr.Color + " enabled=" + dd.GetComponent<MeshRenderer>().enabled + " mat=" + dd.GetComponent<MeshRenderer>().sharedMaterial);
                    }
            if (c.name == "scan_all")
            {
                foreach (var d0 in _model.Drawables)
                {
                    foreach (var d in _model.Drawables) d.GetComponent<MeshRenderer>().enabled = (d == d0);
                    _cam.Render();
                    var t0 = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
                    RenderTexture.active = _rt;
                    t0.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
                    RenderTexture.active = null;
                    int red = 0;
                    foreach (var px in t0.GetPixels32()) if (px.r - px.g > 45 && px.r > 180) red++;
                    Object.DestroyImmediate(t0);
                    if (red > 20) Debug.Log("CielRenderCheck: SCAN red " + d0.name + " " + red);
                }
            }
            if (c.name.StartsWith("only_"))
            {
                foreach (var d in _model.Drawables)
                    if (d.name != c.name.Substring(5).Replace("_L", "").Replace("_R", "")) d.GetComponent<MeshRenderer>().enabled = false;
            }
            _cam.Render();
            var tex = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
            RenderTexture.active = _rt;
            tex.ReadPixels(new Rect(0, 0, Width, Height), 0, 0);
            tex.Apply();
            RenderTexture.active = null;
            var path = Path.Combine(OutDir, c.name + ".png");
            File.WriteAllBytes(path, tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            Debug.Log("CielRenderCheck: wrote " + path);
            if (c.name == "angleX_minus30")
                foreach (var d in _model.Drawables)
                    if (d.name.StartsWith("Mouth")) Debug.Log("CielRenderCheck: drawable " + d.name + " color=" + d.GetComponent<Live2D.Cubism.Rendering.CubismRenderer>().Color + " bounds=" + d.GetComponent<MeshFilter>().sharedMesh.bounds.center);

            _caseIndex++;
            _ticks = 0;
            if (_caseIndex >= Cases.Length)
            {
                EditorApplication.update -= Tick;
                Debug.Log("CIEL_RENDER_CHECK_DONE");
                Finish(0);
            }
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
