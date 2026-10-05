// CIEL compatibility patch for Unity 6.6. Cubism uses int animation-event IDs,
// not native object handles. Keep existing IDs and allocate unused integers;
// never truncate or hash Unity's 64-bit EntityId into this serialized field.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Live2D.Cubism.Framework
{
    public static class CubismMotionEventId
    {
        private static readonly Dictionary<AnimationClip, int> Assigned = new();
        private static readonly HashSet<int> Used = new();
        private static bool scanned;
        private static int next = 1;

        public static int Get(AnimationClip clip)
        {
            foreach (var item in AnimationUtility.GetAnimationEvents(clip))
                if (item.functionName == "InstanceId")
                {
                    Used.Add(item.intParameter);
                    return item.intParameter;
                }
            if (Assigned.TryGetValue(clip, out var value)) return value;
            if (!scanned)
            {
                scanned = true;
                foreach (var guid in AssetDatabase.FindAssets("t:AnimationClip"))
                    foreach (var asset in AssetDatabase.LoadAllAssetsAtPath(AssetDatabase.GUIDToAssetPath(guid)))
                        if (asset is AnimationClip existing)
                            foreach (var item in AnimationUtility.GetAnimationEvents(existing))
                                if (item.functionName == "InstanceId") Used.Add(item.intParameter);
            }
            while (Used.Contains(next)) next = checked(next + 1);
            value = next;
            Used.Add(value);
            Assigned.Add(clip, value);
            return value;
        }
    }
}
#endif
