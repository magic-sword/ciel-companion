// シエルのモデル（Ciel.prefab）に、待機中の呼吸と小さな揺れ（CubismHarmonicMotion）を設定する。
// 値は Live2D 公式の呼吸のサンプル（docs.live2d.com/en/cubism-sdk-manual/breath）を、顔と体は半分程度に控えめにしたもの。
// 実行：Unity.exe -batchmode -projectPath unity -executeMethod Ciel.EditorTools.CielIdleSetup.Run -quit -logFile <log>
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework.HarmonicMotion;
using UnityEditor;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielIdleSetup
    {
        const string PrefabPath = "Assets/Characters/Ciel/Ciel.prefab";

        // パラメーター, 中心（0〜1）, 振れ幅（範囲に対する割合）, 周期（秒）
        static readonly (string id, float origin, float range, float duration)[] Motions =
        {
            ("ParamBreath",     0.5f, 0.5f,   3.2345f),
            ("ParamAngleX",     0.5f, 0.125f, 6.5345f),
            ("ParamAngleY",     0.5f, 0.067f, 3.5345f),
            ("ParamAngleZ",     0.5f, 0.083f, 5.5345f),
            ("ParamBodyAngleZ", 0.5f, 0.1f,  15.5345f),
        };

        public static void Run()
        {
            var root = PrefabUtility.LoadPrefabContents(PrefabPath);
            try
            {
                var model = root.GetComponent<CubismModel>();
                var controller = root.GetComponent<CubismHarmonicMotionController>()
                                 ?? root.AddComponent<CubismHarmonicMotionController>();
                controller.BlendMode = Live2D.Cubism.Framework.CubismParameterBlendMode.Additive;
                foreach (var m in Motions)
                {
                    var p = System.Array.Find(model.Parameters, q => q.Id == m.id);
                    if (p == null) { Debug.LogError("CielIdleSetup: no parameter " + m.id); continue; }
                    var h = p.GetComponent<CubismHarmonicMotionParameter>()
                            ?? p.gameObject.AddComponent<CubismHarmonicMotionParameter>();
                    h.Direction = CubismHarmonicMotionDirection.Centric;
                    h.NormalizedOrigin = m.origin;
                    h.NormalizedRange = m.range;
                    h.Duration = m.duration;
                }
                controller.Refresh();
                PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
                Debug.Log("CIEL_IDLE_SETUP_DONE");
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }
    }
}
