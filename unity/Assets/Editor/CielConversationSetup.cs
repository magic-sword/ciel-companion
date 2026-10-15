// 会話の確認用シーン（Assets/Scenes/Conversation.unity）を作る：カメラ、シエル、会話の部品（CielConversation）と画面の操作（CielConversationUI）、
// シエルに触れる部品（CielTouch）。
// 接続先は Assets/Settings/LiveKitTokenSource.asset（Git 管理外）。LiveKit Cloud の開発用トークンサーバーの ID を
// インスペクターで入れる（種類 DevelopmentTokenServer）。秘密の API キーはアプリに入れない。
// 実行：メニュー CIEL ＞ Conversation ＞ Create Scene、または
//       Unity.exe -batchmode -projectPath unity -executeMethod Ciel.EditorTools.CielConversationSetup.Run -quit -logFile <log>
using System;
using Ciel.Conversation;
using Live2D.Cubism.Framework.MouthMovement;
using LiveKit;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Ciel.EditorTools
{
    public static class CielConversationSetup
    {
        const string ScenePath = "Assets/Scenes/Conversation.unity";
        const string PrefabPath = "Assets/Characters/Ciel/Ciel.prefab";
        const string ConfigPath = "Assets/Settings/LiveKitTokenSource.asset";

        [MenuItem("CIEL/Conversation/Create Scene")]
        public static void Run()
        {
            var config = AssetDatabase.LoadAssetAtPath<TokenSourceComponentConfig>(ConfigPath);
            if (config == null)
            {
                config = ScriptableObject.CreateInstance<TokenSourceComponentConfig>();
                AssetDatabase.CreateAsset(config, ConfigPath);
            }
            var data = new SerializedObject(config);
            // 開発用トークンサーバー（ID は利用者がインスペクターで入れる）
            data.FindProperty("_tokenSourceType").enumValueIndex = (int)TokenSourceType.DevelopmentTokenServer;
            data.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(config);

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
            if (prefab == null) throw new InvalidOperationException("Ciel prefab is missing.");
            var model = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);

            var camera = new GameObject("Main Camera", typeof(Camera), typeof(AudioListener)).GetComponent<Camera>();
            camera.tag = "MainCamera";
            camera.orthographic = true;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.25f, 0.29f, 0.42f);
            camera.GetUniversalAdditionalCameraData().SetRenderer(-1);
            var renderers = model.GetComponentsInChildren<Renderer>();
            var bounds = renderers[0].bounds;
            foreach (var r in renderers) bounds.Encapsulate(r.bounds);
            // 上半身を縦長の画面に収める（頭が上の方に来るように少し上へ）
            camera.transform.position = new Vector3(bounds.center.x, bounds.center.y + bounds.extents.y * 0.1f, bounds.min.z - 10);
            camera.orthographicSize = bounds.extents.y * 1.05f;

            var conv = new GameObject("Conversation", typeof(CielConversation));
            var c = new SerializedObject(conv.GetComponent<CielConversation>());
            c.FindProperty("_tokenConfig").objectReferenceValue = config;
            c.FindProperty("_mouth").objectReferenceValue = model.GetComponent<CubismMouthController>();
            // 表情はモデルの GameObject に付ける（Cubism の更新の順番に入れるため）
            var expression = model.GetComponent<CielExpression>() ?? model.AddComponent<CielExpression>();
            c.FindProperty("_expression").objectReferenceValue = expression;
            c.ApplyModifiedPropertiesWithoutUndo();
            AttachTouch(model, conv.GetComponent<CielConversation>(), camera);
            var ui = conv.AddComponent<CielConversationUI>();
            var u = new SerializedObject(ui);
            u.FindProperty("_conversation").objectReferenceValue = conv.GetComponent<CielConversation>();
            u.ApplyModifiedPropertiesWithoutUndo();

            if (!EditorSceneManager.SaveScene(scene, ScenePath))
                throw new InvalidOperationException("Could not save conversation scene.");
            AssetDatabase.SaveAssets();
            Debug.Log("CIEL_CONVERSATION_SCENE_DONE " + ScenePath);
        }

        // シエルに触れる（CielTouch）をモデルに付ける。表情と同じく、Cubism の更新の順番に入れるためモデルの GameObject に付ける
        static void AttachTouch(GameObject model, CielConversation conversation, Camera camera)
        {
            var touch = model.GetComponent<CielTouch>() ?? model.AddComponent<CielTouch>();
            var t = new SerializedObject(touch);
            t.FindProperty("_model").objectReferenceValue = model.GetComponent<Live2D.Cubism.Core.CubismModel>();
            t.FindProperty("_expression").objectReferenceValue = model.GetComponent<CielExpression>();
            t.FindProperty("_conversation").objectReferenceValue = conversation;
            t.FindProperty("_camera").objectReferenceValue = camera;
            t.ApplyModifiedPropertiesWithoutUndo();
        }

        /// 作成済みの会話シーンに、シエルに触れる部品を足す（シーンを作り直さない。接続の設定はそのまま）
        [MenuItem("CIEL/Conversation/Add Touch")]
        public static void AddTouch()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath);
            var conversation = UnityEngine.Object.FindAnyObjectByType<CielConversation>();
            var expression = UnityEngine.Object.FindAnyObjectByType<CielExpression>();
            if (conversation == null || expression == null) throw new InvalidOperationException("Conversation scene is incomplete.");
            AttachTouch(expression.gameObject, conversation, Camera.main);
            if (!EditorSceneManager.SaveScene(scene)) throw new InvalidOperationException("Could not save conversation scene.");
            Debug.Log("CIEL_CONVERSATION_TOUCH_ADDED " + ScenePath);
        }
    }
}
