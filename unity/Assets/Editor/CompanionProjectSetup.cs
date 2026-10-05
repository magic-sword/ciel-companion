using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace Ciel.Companion.Editor
{
    public static class CompanionProjectSetup
    {
        [MenuItem("CIEL/Apply Project Defaults")]
        public static void Apply()
        {
            PlayerSettings.companyName = "CIEL";
            PlayerSettings.productName = "CIEL Companion";
            PlayerSettings.bundleVersion = "0.1.0";
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
            PlayerSettings.defaultScreenWidth = 540;
            PlayerSettings.defaultScreenHeight = 960;
            PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.ciel.companion");
            PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.iOS, "com.ciel.companion");
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.iOS.microphoneUsageDescription = "シエルとの音声会話にマイクを使用します。";
            EditorSettings.serializationMode = SerializationMode.ForceText;

            foreach (var folder in new[] { "Scripts", "Prefabs", "Characters", "Audio" })
            {
                if (!AssetDatabase.IsValidFolder("Assets/" + folder))
                    AssetDatabase.CreateFolder("Assets", folder);
            }

            const string scenePath = "Assets/Scenes/Main.unity";
            if (!File.Exists(scenePath))
            {
                var scene = EditorSceneManager.OpenScene("Assets/Scenes/SampleScene.unity");
                if (!EditorSceneManager.SaveScene(scene, scenePath))
                    throw new InvalidOperationException("Could not save the main scene.");
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
            AssetDatabase.SaveAssets();
            Validate();
            Debug.Log("CIEL_SETUP_OK: Project defaults saved; Main scene registered.");
        }

        public static void Validate()
        {
            // The Universal 2D template assigns URP per quality level.
            if ((QualitySettings.renderPipeline ?? GraphicsSettings.defaultRenderPipeline) == null)
                throw new InvalidOperationException("URP is not configured.");
            if (!File.Exists("Assets/Scenes/Main.unity"))
                throw new InvalidOperationException("Main scene is missing.");
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Android, BuildTarget.Android))
                throw new InvalidOperationException("Android Build Support is missing.");
            Debug.Log("CIEL_VALIDATE_OK: URP, main scene and Android Build Support are available.");
        }
    }
}
