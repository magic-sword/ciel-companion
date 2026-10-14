// 確定済みの書き出し一式を検証し、必要なときにUnityへ反映する。
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Reflection;
using Ciel.Conversation;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielModelUpdate
    {
        [Serializable] public class FileEntry { public string path; public string sha256; }
        [Serializable] public class Manifest
        {
            public string source_rig;
            public string source_rig_sha256;
            public int material_count;
            public FileEntry[] files;
            public FileEntry[] materials;
        }
        static string Root => Path.GetFullPath(Path.Combine(Application.dataPath, "../.."));
        static string Package => Path.Combine(Root, "assets/ciel/runtime");
        const string TargetAssetPath = "Assets/Characters/Ciel";

        static string SafePath(string root, string relative)
        {
            var path = Path.GetFullPath(Path.Combine(root, relative));
            if (!path.StartsWith(Path.GetFullPath(root) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Invalid package path: " + relative);
            return path;
        }
        static string Hash(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        static Manifest Validate()
        {
            var manifest = JsonUtility.FromJson<Manifest>(File.ReadAllText(Path.Combine(Package, "manifest.json")));
            if (manifest.files == null || manifest.files.Length == 0 || manifest.materials == null || manifest.material_count <= 0 || manifest.materials.Length != manifest.material_count)
                throw new InvalidDataException("Current package manifest is incomplete.");
            if (Hash(SafePath(Root, manifest.source_rig)) != manifest.source_rig_sha256)
                throw new InvalidDataException("Cubism model changed after export. Prepare the package again.");
            foreach (var file in manifest.files)
                if (Hash(SafePath(Package, file.path)) != file.sha256)
                    throw new InvalidDataException("Package checksum mismatch: " + file.path);
            foreach (var file in manifest.materials)
                if (Hash(SafePath(Root, file.path)) != file.sha256)
                    throw new InvalidDataException("Material changed after export: " + file.path);
            foreach (var name in new[] { "Ciel.model3.json", "Ciel.moc3", "Ciel.cdi3.json" })
                if (!manifest.files.Any(f => f.path == name)) throw new InvalidDataException("Missing " + name);
            return manifest;
        }

        [MenuItem("CIEL/Model/Validate Current Package")]
        public static void ValidateCurrent()
        {
            var manifest = Validate();
            VerifyTargets(Path.Combine(Package, "Ciel.moc3"), true);
            var active = Path.Combine(Application.dataPath, "Characters/Ciel/Ciel.moc3");
            VerifyTargets(active, false);
            Debug.Log("CIEL_CURRENT_PACKAGE_VALIDATED " + manifest.files.Length + " files");
        }

        static void VerifyTargets(string path, bool requireNewRig)
        {
            var moc = CubismMoc.CreateFrom(File.ReadAllBytes(path));
            var model = CubismModel.InstantiateFrom(moc);
            try
            {
                var expression = model.gameObject.AddComponent<CielExpression>();
                typeof(CielExpression).GetMethod("Awake", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(expression, null);
                var method = typeof(CielExpression).GetMethod("GetTargets", BindingFlags.Instance | BindingFlags.NonPublic);
                bool modern = model.Parameters.Any(p => p.Id == "ParamRelaxed");
                bool surprise = model.Parameters.Any(p => p.Id == "ParamSurprised");
                if (requireNewRig && !modern) throw new InvalidDataException("Package has no ParamRelaxed.");
                foreach (var name in CielExpression.Names)
                {
                    expression.Set(name);
                    var targets = (Dictionary<string, float>)method.Invoke(expression, null);
                    if (modern)
                    {
                        if (targets["ParamRelaxed"] != (name == "relaxed" ? 1 : 0) || targets["ParamHappy"] != (name == "happy" ? 1 : 0))
                            throw new InvalidDataException("Expression reset failed: " + name);
                        if (name == "relaxed" && (targets.ContainsKey("ParamEyeLOpen") || targets.ContainsKey("ParamMouthForm")))
                            throw new InvalidDataException("Legacy eye narrowing applied to the new relaxed pose.");
                    }
                    else if (name == "relaxed" && targets["ParamEyeLOpen"] != -0.25f)
                        throw new InvalidDataException("Legacy model compatibility failed.");
                    if (surprise)
                    {
                        if (targets["ParamSurprised"] != (name == "surprised" ? 1 : 0))
                            throw new InvalidDataException("Surprise reset failed: " + name);
                        if (name == "surprised" && (targets.ContainsKey("ParamEyeLOpen") || targets.ContainsKey("ParamMouthOpenY")))
                            throw new InvalidDataException("Legacy surprise values applied to the new pose.");
                    }
                    else if (name == "surprised" && targets["ParamMouthOpenY"] != 0.3f)
                        throw new InvalidDataException("Legacy surprise compatibility failed.");
                    bool angry = model.Parameters.Any(p => p.Id == "ParamAngry");
                    bool sad = model.Parameters.Any(p => p.Id == "ParamSad");
                    bool troubled = model.Parameters.Any(p => p.Id == "ParamTroubled");
                    bool embarrassed = model.Parameters.Any(p => p.Id == "ParamEmbarrassed");
                    bool teary = model.Parameters.Any(p => p.Id == "ParamTeary");
                    bool excited = model.Parameters.Any(p => p.Id == "ParamExcited");
                    bool jitome = model.Parameters.Any(p => p.Id == "ParamJitome");
                    if (requireNewRig && !troubled) throw new InvalidDataException("Package has no ParamTroubled.");
                    if (requireNewRig && !embarrassed) throw new InvalidDataException("Package has no ParamEmbarrassed.");
                    if (requireNewRig && !teary) throw new InvalidDataException("Package has no ParamTeary.");
                    if (requireNewRig && !excited) throw new InvalidDataException("Package has no ParamExcited.");
                    if (requireNewRig && !jitome) throw new InvalidDataException("Package has no ParamJitome.");
                    foreach (var control in new[] { "ParamAngry", "ParamSad", "ParamTroubled", "ParamEmbarrassed", "ParamTeary", "ParamExcited", "ParamJitome", "ParamEarFold" })
                    {
                        if (!model.Parameters.Any(p => p.Id == control)) continue;
                        float expected = control == "ParamEarFold" ?
                            ((name == "angry" && angry) || (name == "sad" && sad) || (name == "troubled" && troubled) || (name == "embarrassed" && embarrassed) || (name == "teary" && teary) ? 1 : 0) :
                            (control == "ParamAngry" && name == "angry" || control == "ParamSad" && name == "sad" || control == "ParamTroubled" && name == "troubled" || control == "ParamEmbarrassed" && name == "embarrassed" || control == "ParamTeary" && name == "teary" || control == "ParamExcited" && name == "excited" || control == "ParamJitome" && name == "jitome" ? 1 : 0);
                        if (!targets.TryGetValue(control, out var actual) || actual != expected)
                            throw new InvalidDataException("Expression reset failed: " + name + " " + control);
                    }
                    if ((name == "angry" && angry) || (name == "sad" && sad) || (name == "troubled" && troubled) || (name == "embarrassed" && embarrassed) || (name == "teary" && teary))
                    {
                        if (targets.ContainsKey("ParamEar") || targets.ContainsKey("ParamEyeLOpen") || targets.ContainsKey("ParamMouthForm") || targets.ContainsKey("ParamSweat") || targets.ContainsKey("ParamEyeBallX"))
                            throw new InvalidDataException("Legacy deformation applied to the new pose: " + name);
                        if (name == "embarrassed" && targets["ParamCheek"] != 0f)
                            throw new InvalidDataException("Legacy blush applied to the new embarrassed pose.");
                        if (name == "teary" && (targets.ContainsKey("ParamTear") || targets["ParamCheek"] != 0.25f))
                            throw new InvalidDataException("Legacy tears applied to the new teary pose.");
                    }
                    else if (name == "angry" && targets["ParamEar"] != -0.5f || name == "sad" && targets["ParamEyeLOpen"] != -0.2f || name == "troubled" && targets["ParamSweat"] != 1f || name == "embarrassed" && (targets["ParamEyeBallX"] != 0.6f || targets["ParamCheek"] != 1f) || name == "teary" && targets["ParamTear"] != 1f)
                        throw new InvalidDataException("Legacy sad/angry compatibility failed.");
                    if (name == "excited" && excited)
                    {
                        if (targets.ContainsKey("ParamSparkle") || targets.ContainsKey("ParamEyeLOpen") || targets.ContainsKey("ParamMouthOpenY") || targets.ContainsKey("ParamMouthForm") || targets.ContainsKey("ParamBrowLY") || targets["ParamEar"] != 1f || targets["ParamCheek"] != 0f)
                            throw new InvalidDataException("Legacy values applied to the new excited pose.");
                    }
                    else if (name == "excited" && targets["ParamSparkle"] != 1f)
                        throw new InvalidDataException("Legacy excited compatibility failed.");
                    if (name == "jitome" && jitome)
                    {
                        if (targets.ContainsKey("ParamEyeLOpen") || targets.ContainsKey("ParamMouthForm") || targets["ParamEar"] != -0.35f || targets["ParamCheek"] != 0.15f)
                            throw new InvalidDataException("Legacy values applied to the new jitome pose.");
                    }
                    else if (name == "jitome" && targets["ParamEyeLOpen"] != -0.5f)
                        throw new InvalidDataException("Legacy jitome compatibility failed.");
                }
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(model.gameObject);
                UnityEngine.Object.DestroyImmediate(moc);
            }
            Debug.Log("CIEL_EXPRESSION_TARGETS_VERIFIED modern=" + requireNewRig);
        }

        [MenuItem("CIEL/Model/Apply Current Package")]
        public static void ApplyCurrent()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
                throw new InvalidOperationException("Stop Play mode before updating the Ciel model.");
            var manifest = Validate();
            var target = Path.Combine(Application.dataPath, "Characters/Ciel");
            var backup = Path.Combine(Root, ".local/unity-model-update", DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N"));
            foreach (var path in Directory.GetFiles(target, "*", SearchOption.AllDirectories))
            {
                var dest = SafePath(backup, path.Substring(target.Length + 1));
                Directory.CreateDirectory(Path.GetDirectoryName(dest));
                File.Copy(path, dest);
            }
            // Existing .meta files remain in place so scene and prefab references keep their GUIDs.
            AssetDatabase.StartAssetEditing();
            try
            {
                var installedPath = Path.Combine(target, "runtime-manifest.json");
                if (File.Exists(installedPath))
                {
                    var installed = JsonUtility.FromJson<Manifest>(File.ReadAllText(installedPath));
                    foreach (var old in installed.files)
                        if (!manifest.files.Any(f => f.path == old.path))
                        {
                            SafePath(target, old.path);
                            AssetDatabase.DeleteAsset(TargetAssetPath + "/" + old.path);
                        }
                }
                foreach (var file in manifest.files)
                {
                    var dest = SafePath(target, file.path);
                    Directory.CreateDirectory(Path.GetDirectoryName(dest));
                    File.Copy(SafePath(Package, file.path), dest, true);
                }
                File.Copy(Path.Combine(Package, "manifest.json"), installedPath, true);
            }
            finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            CielIdleSetup.Run();
            AssetDatabase.SaveAssets();
            Debug.Log("CIEL_CURRENT_PACKAGE_APPLIED backup=" + backup);
        }
    }
}
