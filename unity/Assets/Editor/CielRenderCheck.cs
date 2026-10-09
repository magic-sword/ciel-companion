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
            ("eyes_half", 0f, 0f, 0.5f, 0.5f, 0f),
            ("eyes_closed", 0f, 0f, 0f, 0f, 0f),
            ("mouth_small", 0f, 0f, 1f, 1f, 0.5f),
            ("mouth_large", 0f, 0f, 1f, 1f, 1f),
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
