using System;
using System.IO;
using System.Reflection;
using Live2D.Cubism.Core;
using LiveKit;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Ciel.Companion.Editor
{
    public static class CompanionSdkSetup
    {
        private const string RendererPath = "Assets/Live2D/Cubism/Rendering/URP/CubismURPRenderer.asset";
        private const string ModelPath = "Assets/Live2D/Cubism/Samples/Models/Koharu/Koharu.prefab";
        private const string ScenePath = "Assets/Scenes/SdkCheck.unity";
        private const string ConfigPath = "Assets/Settings/LiveKitTokenSource.asset";

        [MenuItem("CIEL/SDK/Configure and Validate")]
        public static void Configure()
        {
            var renderer = AssetDatabase.LoadAssetAtPath<ScriptableRendererData>(RendererPath);
            if (renderer == null) throw new InvalidOperationException("Cubism URP renderer is missing.");
            var pipeline = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>("Assets/Settings/UniversalRP.asset");
            if (pipeline == null) throw new InvalidOperationException("Project URP asset is missing.");
            var serialized = new SerializedObject(pipeline);
            var renderers = serialized.FindProperty("m_RendererDataList");
            var cubismIndex = -1;
            for (var i = 0; i < renderers.arraySize; i++)
                if (renderers.GetArrayElementAtIndex(i).objectReferenceValue == renderer) cubismIndex = i;
            if (cubismIndex < 0)
            {
                cubismIndex = renderers.arraySize;
                renderers.arraySize++;
                renderers.GetArrayElementAtIndex(cubismIndex).objectReferenceValue = renderer;
            }
            serialized.FindProperty("m_DefaultRendererIndex").intValue = cubismIndex;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            pipeline.supportsHDR = false;
            PlayerSettings.colorSpace = ColorSpace.Gamma;
            EditorUtility.SetDirty(pipeline);

            if (!File.Exists(ConfigPath))
            {
                var config = ScriptableObject.CreateInstance<TokenSourceComponentConfig>();
                var configData = new SerializedObject(config);
                configData.FindProperty("_tokenSourceType").enumValueIndex = (int)TokenSourceType.Endpoint;
                configData.ApplyModifiedPropertiesWithoutUndo();
                AssetDatabase.CreateAsset(config, ConfigPath);
            }

            if (!File.Exists(ScenePath)) CreateCheckScene();
            AssetDatabase.SaveAssets();
            Validate();
        }

        private static void CreateCheckScene()
        {
            var previousScene = SceneManager.GetActiveScene();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Additive);
            SceneManager.SetActiveScene(scene);
            try
            {
                var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
                if (prefab == null) throw new InvalidOperationException("Cubism sample prefab is missing.");
                var model = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
                model.name = "Koharu - SDK validation sample";
                var camera = new GameObject("Main Camera", typeof(Camera), typeof(AudioListener)).GetComponent<Camera>();
                camera.tag = "MainCamera";
                camera.orthographic = true;
                camera.orthographicSize = 2.5f;
                camera.transform.position = new Vector3(0, 0, -10);
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.12f, 0.15f, 0.22f);
                camera.GetUniversalAdditionalCameraData().SetRenderer(-1);
                var renderers = model.GetComponentsInChildren<Renderer>();
                if (renderers.Length > 0)
                {
                    var bounds = renderers[0].bounds;
                    foreach (var item in renderers) bounds.Encapsulate(item.bounds);
                    camera.transform.position = new Vector3(bounds.center.x, bounds.center.y, bounds.min.z - 10);
                    camera.orthographicSize = Mathf.Max(bounds.extents.y, bounds.extents.x / (9f / 16f)) * 1.15f;
                }
                if (!EditorSceneManager.SaveScene(scene, ScenePath))
                    throw new InvalidOperationException("Could not save SDK check scene.");
            }
            finally
            {
                if (previousScene.IsValid() && previousScene.isLoaded)
                {
                    SceneManager.SetActiveScene(previousScene);
                    EditorSceneManager.CloseScene(scene, true);
                }
            }
        }

        [MenuItem("CIEL/SDK/Validate Installation")]
        public static void Validate()
        {
            ValidateMotionIds();
            var mocVersion = CubismMoc.LatestVersion; // Calls the native Cubism Core DLL.
            if (mocVersion == 0) throw new InvalidOperationException("Cubism Core returned an invalid version.");
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            var model = prefab != null ? prefab.GetComponent<CubismModel>() : null;
            if (model == null || model.Drawables.Length == 0)
                throw new InvalidOperationException("Cubism sample model was not imported correctly.");

            // Validate the SDK's own native initialization without connecting or recording.
            var ffiType = typeof(Room).Assembly.GetType("LiveKit.Internal.FFI.FfiClient", true);
            var ffi = ffiType.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static).GetValue(null);
            if (!(bool)ffiType.GetMethod("Initialized").Invoke(ffi, null))
                ffiType.GetMethod("Initialize").Invoke(ffi, null);
            if (!(bool)ffiType.GetMethod("Initialized").Invoke(ffi, null))
                throw new InvalidOperationException("LiveKit native initialization failed.");
            if (AssetDatabase.LoadAssetAtPath<TokenSourceComponentConfig>(ConfigPath) == null)
                throw new InvalidOperationException("LiveKit token source configuration is missing.");
            Debug.Log($"CIEL_SDK_OK: Cubism native MOC version={mocVersion}, sample drawables={model.Drawables.Length}; LiveKit native SDK initialized. No network session or microphone used.");
        }

        private static void ValidateMotionIds()
        {
            var first = new AnimationClip();
            var second = new AnimationClip();
            try
            {
                AnimationUtility.SetAnimationEvents(first, new[] {
                    new AnimationEvent { functionName = "InstanceId", intParameter = -1234567 }
                });
                var preserved = Live2D.Cubism.Framework.CubismMotionEventId.Get(first);
                var allocated = Live2D.Cubism.Framework.CubismMotionEventId.Get(second);
                if (preserved != -1234567 || allocated == preserved || allocated == 0 ||
                    allocated != Live2D.Cubism.Framework.CubismMotionEventId.Get(second))
                    throw new InvalidOperationException("Cubism motion event ID compatibility check failed.");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(first);
                UnityEngine.Object.DestroyImmediate(second);
            }
        }
    }
}
