// アプリのビルド（Windows・Android）。Unity の標準のビルド（BuildPipeline.BuildPlayer）を、決まった設定で呼ぶだけ。
// 標準の File ＞ Build Profiles からでもビルドできるが、ここを通すと、シーン・出力先・プレイヤー設定がいつも同じになり、
// エディタを開かずにコマンドからもビルドできる。出力は Builds/（Git 管理外）。
// ビルドには接続の設定（Assets/Settings/LiveKitTokenSource.asset）が入るので、ビルドしたものは配らない。
// 使い方は docs/build-ja.md。
using System;
using System.IO;
using UnityEditor;
#if UNITY_ANDROID
using UnityEditor.Android;
#endif
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Ciel.Companion.Editor
{
    public static class CielBuild
    {
        const string Scene = "Assets/Scenes/Conversation.unity";

        /// Windows：会議に OBS で取り込んで使う。OBS や会議のブラウザを操作しても会話が止まらないように、
        /// 前面でなくても動かし、ウィンドウで開く
        [MenuItem("CIEL/Build/Windows")]
        public static void Windows()
        {
            PlayerSettings.runInBackground = true;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.resizableWindow = true;
            Build(BuildTarget.StandaloneWindows64, "Builds/Windows/CIEL Companion.exe");
        }

        /// Android：開発用の APK（Unity の開発用の鍵で署名）。端末へは adb install で入れる
        [MenuItem("CIEL/Build/Android")]
        public static void Android()
        {
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.forceInternetPermission = true;   // LiveKit へつなぐ
            EditorUserBuildSettings.buildAppBundle = false;          // ストア用の AAB ではなく、直接入れられる APK
            Build(BuildTarget.Android, "Builds/Android/CIEL Companion.apk");
        }

        static void Build(BuildTarget target, string output)
        {
            AssetDatabase.SaveAssets();
            var group = BuildPipeline.GetBuildTargetGroup(target);
            if (!BuildPipeline.IsBuildTargetSupported(group, target))
                throw new InvalidOperationException($"CIEL_BUILD_FAILED: {target} のビルドの機能（Unity Hub のモジュール）が入っていない");
            if (EditorUserBuildSettings.activeBuildTarget != target)
                EditorUserBuildSettings.SwitchActiveBuildTarget(group, target);   // 初回は素材の読み込み直しで時間がかかる

            Directory.CreateDirectory(Path.GetDirectoryName(output));
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { Scene },
                locationPathName = output,
                target = target,
                options = BuildOptions.None,
            });
            var s = report.summary;
            if (s.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"CIEL_BUILD_FAILED: {target} {s.result}（エラー {s.totalErrors} 件）");
            Debug.Log($"CIEL_BUILD_OK: {s.outputPath}（{s.totalSize / 1024 / 1024} MB、{s.totalTime.TotalSeconds:0} 秒）");
        }
    }

#if UNITY_ANDROID   // Android のモジュールが無い環境でもコンパイルできるように（Android のビルド中は Android が選ばれている）
    /// Android の権限を、Unity が作る Android のプロジェクトの AndroidManifest.xml に足す。
    /// マイクの許可を求める画面は LiveKit の PlatformAudio が録音の開始のときに出すが、権限の宣言が無いと許可を求められない。
    /// 手書きの AndroidManifest.xml を置かないのは、Unity 6 の起動の仕組み（GameActivity）と食い違わないようにするため
    sealed class CielAndroidPermissions : IPostGenerateGradleAndroidProject
    {
        static readonly string[] Permissions =
        {
            "android.permission.INTERNET",
            "android.permission.RECORD_AUDIO",           // マイク
            "android.permission.MODIFY_AUDIO_SETTINGS",  // WebRTC が通話用の音声の設定（エコー除去など）に切り替える
        };

        public int callbackOrder => 0;

        public void OnPostGenerateGradleAndroidProject(string path)
        {
            var manifest = Path.Combine(path, "src", "main", "AndroidManifest.xml");
            var xml = File.ReadAllText(manifest);
            var added = "";
            foreach (var p in Permissions)
                if (!xml.Contains($"\"{p}\"")) added += $"\n  <uses-permission android:name=\"{p}\" />";
            if (added.Length == 0) return;
            var i = xml.IndexOf("<application", StringComparison.Ordinal);
            if (i < 0) throw new InvalidOperationException($"AndroidManifest.xml に <application> が無い: {manifest}");
            File.WriteAllText(manifest, xml.Insert(i, added.TrimStart('\n') + "\n  "));
            Debug.Log($"[CielBuild] Android の権限を足した：{added.Replace("\n", " ").Trim()}");
        }
    }
#endif
}
