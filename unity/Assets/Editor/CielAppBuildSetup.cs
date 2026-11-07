// 既存の会話シーンを一度だけ共通 Prefab に移し、製品ごとの薄い起動シーンを作る。
using System;
using Ciel.Conversation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Ciel.EditorTools
{
    public static class CielAppBuildSetup
    {
        public const string RuntimePath = "Assets/Prefabs/CielRuntime.prefab";
        public const string CompanionScene = "Assets/Scenes/Conversation.unity";
        public const string BroadcastScene = "Assets/Scenes/Broadcast.unity";
        public const string CompanionProfile = "Assets/Settings/CompanionApp.asset";
        public const string BroadcastProfile = "Assets/Settings/BroadcastApp.asset";

        [MenuItem("CIEL/Apps/Create Shared Runtime and App Scenes")]
        public static void Run()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Prefabs")) AssetDatabase.CreateFolder("Assets", "Prefabs");
            EditorSceneManager.OpenScene(CompanionScene);
            if (AssetDatabase.LoadAssetAtPath<GameObject>(RuntimePath) == null
                || UnityEngine.Object.FindAnyObjectByType<CielAppComposition>() == null) ExtractRuntime();
            Profile(CompanionProfile, false);
            Profile(BroadcastProfile, true);
            AssetDatabase.SaveAssets();
            CreateScene(CompanionScene, CompanionProfile);
            CreateScene(BroadcastScene, BroadcastProfile);
            EditorSceneManager.OpenScene(CompanionScene);
            AssetDatabase.SaveAssets();
            Debug.Log("CIEL_APP_SCENES_OK");
        }

        static void ExtractRuntime()
        {
            var scene = EditorSceneManager.OpenScene(CompanionScene);
            if (UnityEngine.Object.FindAnyObjectByType<CielConversation>() == null)
                throw new InvalidOperationException("The existing conversation scene has no shared runtime.");
            var roots = scene.GetRootGameObjects();
            var root = new GameObject("Ciel Runtime");
            foreach (var go in roots) go.transform.SetParent(root.transform, true);
            foreach (var ui in root.GetComponentsInChildren<CielConversationUI>(true)) UnityEngine.Object.DestroyImmediate(ui);
            if (root.GetComponentInChildren<CielBackground>(true) == null) root.AddComponent<CielBackground>();
            if (PrefabUtility.SaveAsPrefabAsset(root, RuntimePath) == null)
                throw new InvalidOperationException("Could not create the shared runtime prefab.");
        }

        static CielAppProfile Profile(string path, bool broadcast)
        {
            var existing = AssetDatabase.LoadAssetAtPath<CielAppProfile>(path);
            if (existing != null) return existing;   // 利用者の調整を作り直しで上書きしない
            var profile = ScriptableObject.CreateInstance<CielAppProfile>();
            profile.broadcast = broadcast;
            profile.windowSize = broadcast ? new Vector2Int(1100, 800) : new Vector2Int(540, 960);
            profile.openOutputOnStart = broadcast;
            profile.showStatusOnOutput = false;   // 詳細は操作画面。映像への札は任意に有効にする
            AssetDatabase.CreateAsset(profile, path);
            return profile;
        }

        static void CreateScene(string path, string profilePath)
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            // NewScene が未参照アセットを解放するので、シーン切替後に読み直す。
            var profile = AssetDatabase.LoadAssetAtPath<CielAppProfile>(profilePath);
            var runtime = AssetDatabase.LoadAssetAtPath<GameObject>(RuntimePath);
            PrefabUtility.InstantiatePrefab(runtime, scene);
            var shell = new GameObject(profile.broadcast ? "Broadcast App" : "Companion App").AddComponent<CielAppComposition>();
            var so = new SerializedObject(shell);
            so.FindProperty("_profile").objectReferenceValue = profile;
            so.ApplyModifiedPropertiesWithoutUndo();
            if (so.FindProperty("_profile").objectReferenceValue == null)
                throw new InvalidOperationException("App profile reference is missing: " + profilePath);
            if (!EditorSceneManager.SaveScene(scene, path)) throw new InvalidOperationException("Could not save " + path);
        }
    }
}
