// 開いたシーンの Main Camera の映りを画像に保存する（編集時。確認用）。
// 実行：Unity.exe -batchmode -projectPath unity -executeMethod Ciel.EditorTools.CielSceneShot.Run -quit -logFile <log>
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielSceneShot
    {
        public static void Run()
        {
            EditorSceneManager.OpenScene("Assets/Scenes/Conversation.unity");
            var cam = Camera.main;
            var rt = new RenderTexture(540, 960, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
            Directory.CreateDirectory("../.local/render-check");
            File.WriteAllBytes("../.local/render-check/conversation-scene.png", tex.EncodeToPNG());
            cam.targetTexture = null;
            Debug.Log($"CIEL_SCENE_SHOT cam pos={cam.transform.position} size={cam.orthographicSize} renderers={Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None).Length}");
        }
    }
}
