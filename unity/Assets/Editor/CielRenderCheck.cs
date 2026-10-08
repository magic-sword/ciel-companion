using System.IO;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace Ciel.EditorTools
{
    /// <summary>
    /// 書き出したシエルのモデルを、パラメーターを変えながら画像に描画して確認する。
    /// 再生モードに入り、1ケースごとに数フレーム進めてから撮影する（Cubismの描画はフレームごとにメッシュを切り替えるため）。
    /// 実行: Unity -batchmode -executeMethod Ciel.EditorTools.CielRenderCheck.Run -logFile &lt;path&gt;
    /// 出力: .local/render-check/*.png（Git対象外）
    /// </summary>
    public static class CielRenderCheck
    {
        const string PrefabPath = "Assets/Characters/Ciel/Ciel.prefab";
        const string StateKey = "CielRenderCheck.Pending";

        // 名前, ParamAngleX, ParamAngleY, ParamEyeLOpen, ParamEyeROpen
        static readonly (string name, float angleX, float angleY, float eyeL, float eyeR)[] Cases =
        {
            ("neutral", 0f, 0f, 1f, 1f),
            ("angleX_minus30", -30f, 0f, 1f, 1f),
            ("angleX_plus30", 30f, 0f, 1f, 1f),
            ("eyes_half", 0f, 0f, 0.5f, 0.5f),
            ("eyes_closed", 0f, 0f, 0f, 0f),
        };

        public static void Run()
        {
            // 再生モードへ入る。ドメインが再読込されるので、状態は SessionState に置く。
            SessionState.SetBool(StateKey, true);
            EditorApplication.EnterPlaymode();
        }

        [InitializeOnLoadMethod]
        static void OnLoad()
        {
            EditorApplication.playModeStateChanged += state =>
            {
                if (state == PlayModeStateChange.EnteredPlayMode && SessionState.GetBool(StateKey, false))
                {
                    SessionState.SetBool(StateKey, false);
                    var go = new GameObject("CielRenderCheckRunner");
                    go.AddComponent<Runner>();
                }
            };
        }

        sealed class Runner : MonoBehaviour
        {
            CubismModel _model;
            (string name, float angleX, float angleY, float eyeL, float eyeR) _current;

            // Cubismはパラメーターを毎フレーム保存値へ戻すので、値はLateUpdateで設定する。
            void LateUpdate()
            {
                if (_model == null) return;
                Set(_model, "ParamAngleX", _current.angleX);
                Set(_model, "ParamAngleY", _current.angleY);
                Set(_model, "ParamEyeLOpen", _current.eyeL);
                Set(_model, "ParamEyeROpen", _current.eyeR);
                _model.ForceUpdateNow();
            }

            System.Collections.IEnumerator Start()
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
                if (prefab == null)
                {
                    Debug.LogError("CielRenderCheck: prefab not found: " + PrefabPath);
                    EditorApplication.Exit(2);
                    yield break;
                }

                var outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/render-check"));
                Directory.CreateDirectory(outDir);

                var instance = Instantiate(prefab);
                var model = instance.GetComponent<CubismModel>();
                _model = model;
                _current = Cases[0];
                Debug.Log("CielRenderCheck: drawables=" + model.Drawables.Length + " parameters=" + model.Parameters.Length);

                var camGo = new GameObject("CielRenderCheckCamera");
                var cam = camGo.AddComponent<Camera>();
                cam.orthographic = true;
                cam.orthographicSize = 0.75f;
                cam.transform.position = new Vector3(0f, 0f, -10f);
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0.25f, 0.3f, 0.45f, 1f);
                const int width = 768, height = 1024;
                var rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
                cam.targetTexture = rt;

                for (int i = 0; i < 5; i++) yield return null;   // 初回の更新を待つ

                foreach (var c in Cases)
                {
                    _current = c;
                    for (int i = 0; i < 5; i++) yield return null;
                    yield return new WaitForEndOfFrame();

                    LogState(model, c.name);
                    cam.Render();
                    var tex = new Texture2D(width, height, TextureFormat.RGBA32, false);
                    RenderTexture.active = rt;
                    tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                    tex.Apply();
                    RenderTexture.active = null;
                    var path = Path.Combine(outDir, c.name + ".png");
                    File.WriteAllBytes(path, tex.EncodeToPNG());
                    Destroy(tex);
                    Debug.Log("CielRenderCheck: wrote " + path);
                }

                Debug.Log("CIEL_RENDER_CHECK_DONE");
                EditorApplication.Exit(0);
            }

            static void LogState(CubismModel model, string label)
            {
                float ax = float.NaN, el = float.NaN;
                foreach (var p in model.Parameters)
                {
                    if (p.Id == "ParamAngleX") ax = p.Value;
                    if (p.Id == "ParamEyeLOpen") el = p.Value;
                }
                string v = "n/a";
                foreach (var d in model.Drawables)
                {
                    if (d.name == "Face_Skin")
                    {
                        var vp = d.VertexPositions;
                        v = vp.Length > 0 ? vp[vp.Length / 2].ToString("F4") : "empty";
                        var mr = d.GetComponent<MeshRenderer>();
                        var mf = d.GetComponent<MeshFilter>();
                        Debug.Log("CielState[" + label + "] Face_Skin renderer.enabled=" + mr.enabled + " meshVerts=" + (mf.sharedMesh != null ? mf.sharedMesh.vertexCount : -1) + " meshMid=" + (mf.sharedMesh != null && mf.sharedMesh.vertexCount > 0 ? mf.sharedMesh.vertices[mf.sharedMesh.vertexCount / 2].ToString("F4") : "n/a"));
                    }
                }
                Debug.Log("CielState[" + label + "] ParamAngleX=" + ax + " ParamEyeLOpen=" + el + " FaceSkinMidVertex=" + v + " frame=" + Time.frameCount);
            }

            static void Set(CubismModel model, string id, float value)
            {
                foreach (var p in model.Parameters)
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
}
