// 会話サーバーの声の大きさ（RMS）を測り、音は消す（声の再生は端末の音声が行うので、ここで鳴らすと二重になる）。
// AudioStream が音を書き込んだ後に読むため、AudioStream を作った後に AddComponent すること。
using UnityEngine;

namespace Ciel.Conversation
{
    public sealed class AgentVoiceMeter : MonoBehaviour
    {
        volatile float _level;

        /// 直近の声の大きさ（0〜1 くらい。話していないとき 0）
        public float Level => _level;

        void OnAudioFilterRead(float[] data, int channels)
        {
            // Unity の音声スレッドから呼ばれる
            double sum = 0;
            for (int i = 0; i < data.Length; i++) sum += data[i] * data[i];
            _level = data.Length > 0 ? Mathf.Sqrt((float)(sum / data.Length)) : 0f;
            System.Array.Clear(data, 0, data.Length);
        }
    }
}
