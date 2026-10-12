// シエルとの音声会話（フェーズ1）。LiveKit のルームに入り、マイクを送り、会話サーバー（server/agent）の声を再生し、
// その声の大きさで口を動かす。
//
// 流れ：トークンを取得（TokenSourceComponent）→ 端末の音声（WebRTC のエコー除去つき）を用意 → ルームへ接続
//       → マイクを公開 → 会話サーバーの音声トラックが届いたら、口パク用の音量を測る。
// 声の再生は端末の音声（PlatformAudio）が自動で行う。口パク用には同じトラックを Unity の AudioSource でも受け、
// 音量だけ測って音は消す（二重に鳴らさない）。
// LiveKit の Agents サンプル（Samples~/Agents、Apache-2.0）の接続手順を参考にした。
using System.Collections;
using LiveKit;
using LiveKit.Proto;
using Live2D.Cubism.Framework.MouthMovement;
using UnityEngine;
using RoomOptions = LiveKit.RoomOptions;

namespace Ciel.Conversation
{
    [RequireComponent(typeof(TokenSourceComponent))]
    public sealed class CielConversation : MonoBehaviour
    {
        [SerializeField] CubismMouthController _mouth;
        [SerializeField] bool _connectOnStart = true;
        [Tooltip("使いたいマイクの名前の一部（空なら一覧の順に試す）")]
        [SerializeField] string _preferredMic = "";
        [Tooltip("口の開きの倍率（声の大きさ → 口の開き）")]
        [SerializeField] float _mouthGain = 6f;
        [Tooltip("口が開くときと閉じるときのなめらかさ（秒）")]
        [SerializeField] float _openTime = 0.04f, _closeTime = 0.10f;

        Room _room;
        PlatformAudio _platformAudio;
        PlatformAudioSource _micSource;
        LocalAudioTrack _micTrack;
        AudioStream _voiceStream;
        AgentVoiceMeter _meter;
        bool _quitting;

        public bool IsConnected => _room != null;

        void Start()
        {
            if (_mouth != null) _mouth.BlendMode = Live2D.Cubism.Framework.CubismParameterBlendMode.Override;
            if (_connectOnStart) StartCoroutine(Connect());
        }

        public void StartConversation()
        {
            if (_room == null) StartCoroutine(Connect());
        }

        IEnumerator Connect()
        {
            var fetch = GetComponent<TokenSourceComponent>().FetchConnectionDetails();
            yield return fetch;
            if (fetch.IsError)
            {
                Debug.LogError($"[CielConversation] トークンを取得できない: {fetch.Exception?.Message}");
                yield break;
            }
            var details = fetch.Result;

            // 端末の音声は、ルームへ接続する前に作る（後から作ると、届いた声が再生されない）
            try
            {
                _platformAudio = new PlatformAudio();
                var (rec, play) = _platformAudio.GetDevices();
                foreach (var d in rec) Debug.Log($"[CielConversation] マイク {d.Index}: {d.Name}");
                foreach (var d in play) Debug.Log($"[CielConversation] スピーカー {d.Index}: {d.Name}");
                if (_platformAudio.PlayoutDeviceCount > 0) _platformAudio.SetPlayoutDevice(0);
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[CielConversation] 端末の音声を用意できない: {e.Message}");
                yield break;
            }

            _room = new Room();
            _room.TrackSubscribed += OnTrackSubscribed;
            _room.TrackUnsubscribed += OnTrackUnsubscribed;
            yield return _room.Connect(details.ServerUrl, details.ParticipantToken, new RoomOptions());
            Debug.Log($"[CielConversation] ルーム '{_room.Name}' に接続した");

            // マイク（OS の許可を求める）。使えるマイクが見つかるまで順に試す。見つからなければ、聞くだけで続ける
            yield return StartMicrophone();
            if (!_recording)
            {
                Debug.LogWarning("[CielConversation] 使えるマイクがない。シエルの声を聞くだけで続ける");
                yield break;
            }
            // エコー除去・雑音除去・自動音量を有効にする
            _micSource = new PlatformAudioSource(_platformAudio, AudioProcessingOptions.Default);
            _micTrack = LocalAudioTrack.CreateAudioTrack("ciel-user-mic", _micSource, _room);
            var publish = _room.LocalParticipant.PublishTrack(_micTrack, new TrackPublishOptions
            {
                AudioEncoding = new AudioEncoding { MaxBitrate = 64000 },
                Source = TrackSource.SourceMicrophone
            });
            yield return publish;
            if (publish.IsError)
            {
                Debug.LogError("[CielConversation] マイクを公開できない");
                EndConversation();
                yield break;
            }
            Debug.Log("[CielConversation] 会話の準備ができた");
        }

        bool _recording;

        // 録音機器を、指定の名前（_preferredMic を含むもの）→ 一覧の順 に試す。
        // StartRecording は失敗すると例外を投げるので、列挙子を手で進めて受け止める（エラーで再生が一時停止しないように）
        IEnumerator StartMicrophone()
        {
            _recording = false;
            var (rec, _) = _platformAudio.GetDevices();
            var order = new System.Collections.Generic.List<AudioDevice>(rec);
            if (!string.IsNullOrEmpty(_preferredMic))
                order.Sort((a, b) => (b.Name?.Contains(_preferredMic) == true ? 1 : 0) - (a.Name?.Contains(_preferredMic) == true ? 1 : 0));
            foreach (var d in order)
            {
                try { _platformAudio.SetRecordingDevice(d.Guid ?? ""); }
                catch (System.Exception e) { Debug.LogWarning($"[CielConversation] マイク '{d.Name}' を選べない: {e.Message}"); continue; }
                var it = _platformAudio.StartRecording();
                while (true)
                {
                    object current;
                    try
                    {
                        if (!it.MoveNext()) { _recording = true; break; }
                        current = it.Current;
                    }
                    catch (System.Exception e)
                    {
                        Debug.LogWarning($"[CielConversation] マイク '{d.Name}' を開けない: {e.Message}");
                        break;
                    }
                    yield return current;
                }
                if (_recording)
                {
                    Debug.Log($"[CielConversation] マイク '{d.Name}' を使う");
                    yield break;
                }
            }
        }

        void OnTrackSubscribed(IRemoteTrack track, RemoteTrackPublication publication, RemoteParticipant participant)
        {
            if (!(track is RemoteAudioTrack audio) || _voiceStream != null) return;
            // 口パク用：音量だけを測る AudioSource（音は AgentVoiceMeter が消す）
            var go = new GameObject("CielVoiceMeter");
            go.transform.SetParent(transform, false);
            var source = go.AddComponent<AudioSource>();
            _voiceStream = new AudioStream(audio, source);
            _meter = go.AddComponent<AgentVoiceMeter>();   // AudioStream の後に付けて、届いた音を読む
            Debug.Log($"[CielConversation] {participant.Identity} の声を受信");
        }

        void OnTrackUnsubscribed(IRemoteTrack track, RemoteTrackPublication publication, RemoteParticipant participant)
        {
            if (track is RemoteAudioTrack) DisposeVoice();
        }

        void DisposeVoice()
        {
            _voiceStream?.Dispose();
            _voiceStream = null;
            if (_meter != null) Destroy(_meter.gameObject);
            _meter = null;
        }

        float _mouthValue;

        void Update()
        {
            if (_mouth == null) return;
            var target = _meter != null ? Mathf.Clamp01(_meter.Level * _mouthGain) : 0f;
            var t = target > _mouthValue ? _openTime : _closeTime;
            _mouthValue = Mathf.MoveTowards(_mouthValue, target, Time.deltaTime / Mathf.Max(t, 1e-3f));
            _mouth.MouthOpening = _mouthValue;
        }

        public void EndConversation()
        {
            DisposeVoice();
            if (_micTrack != null && _room != null) _room.LocalParticipant.UnpublishTrack(_micTrack, stopOnUnpublish: false);
            _micTrack = null;
            if (_platformAudio != null && _recording)
            {
                _recording = false;
                try { _platformAudio.StopRecording(); } catch (System.Exception e) { Debug.LogWarning(e.Message); }
            }
            _micSource?.Dispose();
            _micSource = null;
            _platformAudio?.Dispose();
            _platformAudio = null;
            if (_room != null)
            {
                _room.TrackSubscribed -= OnTrackSubscribed;
                _room.TrackUnsubscribed -= OnTrackUnsubscribed;
                _room.Disconnect();
                _room = null;
            }
            if (_mouth != null) _mouth.MouthOpening = 0f;
        }

        void OnApplicationQuit() => _quitting = true;

        void OnDestroy()
        {
            // 終了時は SDK の部品が先に壊れていることがあるので、片付けは OS に任せる（サンプルと同じ）
            if (!_quitting) EndConversation();
        }
    }
}
