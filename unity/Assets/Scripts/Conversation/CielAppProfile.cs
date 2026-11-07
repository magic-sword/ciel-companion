using UnityEngine;

namespace Ciel.Conversation
{
    // シーンは起動時の構成だけを持つ。会話・音声・モデルは同じ Runtime Prefab を使う。
    [CreateAssetMenu(menuName = "CIEL/App Profile")]
    public sealed class CielAppProfile : ScriptableObject
    {
        public bool broadcast;
        public Vector2Int windowSize = new Vector2Int(540, 960);
        public bool openOutputOnStart;
        public bool showStatusOnOutput;
    }
}
