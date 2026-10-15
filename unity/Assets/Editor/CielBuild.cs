// Windows 用のビルド（会議に OBS で取り込んで使う）。出力は Builds/Windows（Git 管理外）。
// 会議では OBS や会議のブラウザを操作するので、アプリが前面でなくても動き続けるようにし、ウィンドウで開く。
// ビルドには接続の設定（Assets/Settings/LiveKitTokenSource.asset）が入るので、ビルドしたものは配らない。
// Editor を閉じて：.\scripts\unity.ps1 run . --timeout 1800 --log-file ./Logs/build-windows.log -- -executeMethod Ciel.Companion.Editor.CielBuild.Windows
using System;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Ciel.Companion.Editor
{
    public static class CielBuild
    {
        const string Scene = "Assets/Scenes/Conversation.unity";
        const string Output = "Builds/Windows/CIEL Companion.exe";

        [MenuItem("CIEL/Build/Windows")]
        public static void Windows()
        {
            PlayerSettings.runInBackground = true;   // 前面でなくても会話を続ける
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.resizableWindow = true;
            AssetDatabase.SaveAssets();

            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { Scene },
                locationPathName = Output,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            });
            var s = report.summary;
            if (s.result != BuildResult.Succeeded)
                throw new InvalidOperationException($"CIEL_BUILD_FAILED: {s.result}（エラー {s.totalErrors} 件）");
            Debug.Log($"CIEL_BUILD_OK: {s.outputPath}（{s.totalSize / 1024 / 1024} MB、{s.totalTime.TotalSeconds:0} 秒）");
        }
    }
}
