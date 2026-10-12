// シエルとの音声会話（フェーズ1）。LiveKit のルームに入り、会話サーバー（server/agent）の声を再生し、
// その声の大きさで口を動かす。マイクは最初は切っておき、SetMicEnabled（画面のマイクボタン）で入れる。
//
// 流れ：トークンを取得（UnityWebRequest。設定は TokenSourceComponentConfig）→ 端末の音声（WebRTC のエコー除去つき）を用意 → ルームへ接続
//       → 会話サーバーの音声トラックが届いたら、口パク用の音量を測る。
//       マイクを入れると、録音を始めて（初回はトラックを公開）、切ると録音を止めてトラックをミュートする。
// 声の再生は端末の音声（PlatformAudio）が自動で行う。口パク用には同じトラックを Unity の AudioSource でも受け、
// 音量だけ測って音は消す（二重に鳴らさない）。
// マイクの機器：PC は OS の一覧から選べる（既定は OS の既定のマイク）。スマホは OS が切り替えを管理するので選ばない。
// LiveKit の Agents サンプル（Samples~/Agents、Apache-2.0）の接続手順を参考にした。
using System;
using System.Collections;
using System.Collections.Generic;
using LiveKit;
using LiveKit.Proto;
using Live2D.Cubism.Framework.MouthMovement;
using UnityEngine;
using RoomOptions = LiveKit.RoomOptions;

namespace Ciel.Conversation
{
    public sealed class CielConversation : MonoBehaviour
    {
        [SerializeField] CubismMouthController _mouth;
        [Tooltip("接続の設定（Assets/Settings/LiveKitTokenSource.asset）")]
        [SerializeField] TokenSourceComponentConfig _tokenConfig;
        [SerializeField] bool _connectOnStart = true;
        [Tooltip("口の開きの倍率（声の大きさ → 口の開き）")]
        [SerializeField] float _mouthGain = 6f;
        [Tooltip("口が開くときと閉じるときのなめらかさ（秒）")]
        [SerializeField] float _openTime = 0.04f, _closeTime = 0.10f;

        const string MicPrefKey = "ciel.micDevice";

        Room _room;
        PlatformAudio _platformAudio;
        PlatformAudioSource _micSource;
        LocalAudioTrack _micTrack;
        AudioStream _voiceStream;
        AgentVoiceMeter _meter;
        bool _recording, _busy, _quitting;
        string _micGuid;   // 選んだマイク。null は OS の既定

        public enum State { Disconnected, Connecting, Connected, Failed }
        public State Status { get; private set; } = State.Disconnected;
        public bool MicEnabled => _recording;
        public bool MicBusy => _busy;
        /// 状態が変わったとき（画面の表示の更新用）
        public event Action Changed;

        /// PC ならマイクの一覧（名前、ID）。スマホは空（OS に任せる）
        public List<(string name, string guid)> MicDevices { get; } = new List<(string, string)>();
        public bool CanSelectMic => Application.isMobilePlatform == false && MicDevices.Count > 0;
        public string SelectedMic => _micGuid;

        void Start()
        {
            if (_mouth != null) _mouth.BlendMode = Live2D.Cubism.Framework.CubismParameterBlendMode.Override;
            _micGuid = PlayerPrefs.HasKey(MicPrefKey) ? PlayerPrefs.GetString(MicPrefKey) : null;
            if (_connectOnStart) StartConversation();
        }

        public void StartConversation()
        {
            if (_room == null && Status != State.Connecting) StartCoroutine(Connect());
        }

        void SetStatus(State s)
        {
            Status = s;
            Changed?.Invoke();
        }

        static void Trace(string what) =>
            Debug.Log($"[CielConversation] {what}（frame={Time.frameCount}, t={Time.realtimeSinceStartup:0.00}）");

        IEnumerator Connect()
        {
            SetStatus(State.Connecting);
            Trace("トークンを取得");
            string serverUrl = null, token = null;
            yield return FetchToken((u, t) => { serverUrl = u; token = t; });
            Trace("トークンを取得した");
            if (string.IsNullOrEmpty(token))
            {
                SetStatus(State.Failed);
                yield break;
            }

            // 端末の音声は、ルームへ接続する前に作る（後から作ると、届いた声が再生されない）
            try
            {
                Trace("端末の音声を作る");
                _platformAudio = new PlatformAudio();
                Trace("端末の音声を作った");
                var (rec, play) = _platformAudio.GetDevices();
                MicDevices.Clear();
                foreach (var d in rec)
                {
                    Debug.Log($"[CielConversation] マイク {d.Index}: {d.Name}");
                    if (!string.IsNullOrEmpty(d.Guid)) MicDevices.Add((d.Name, d.Guid));
                }
                foreach (var d in play) Debug.Log($"[CielConversation] スピーカー {d.Index}: {d.Name}");
                // 保存していたマイクが今は無いなら、既定に戻す
                if (_micGuid != null && !MicDevices.Exists(m => m.guid == _micGuid)) _micGuid = null;
            }
            catch (Exception e)
            {
                Debug.LogError($"[CielConversation] 端末の音声を用意できない: {e.Message}");
                SetStatus(State.Failed);
                yield break;
            }

            _room = new Room();
            _room.TrackSubscribed += OnTrackSubscribed;
            _room.TrackUnsubscribed += OnTrackUnsubscribed;
            Trace("ルームへ接続");
            yield return _room.Connect(serverUrl, token, new RoomOptions());
            Debug.Log($"[CielConversation] ルーム '{_room.Name}' に接続した（マイクは切ってある）");
            SetStatus(State.Connected);
        }

        [System.Serializable]
        class ConnectionDetailsJson
        {
            public string server_url;
            public string participant_token;
        }

        // 接続のトークンを取る。LiveKit の TokenSourceComponent は .NET の HttpClient を使い、エディタの再生中に
        // スクリプトの再読み込みが起きて、シエルが描かれなくなった。Unity の UnityWebRequest で同じ要求を送る。
        // 開発用トークンサーバー（DevelopmentTokenServer）と、任意の取得先（Endpoint）に対応する。
        IEnumerator FetchToken(Action<string, string> done)
        {
            var config = _tokenConfig;
            string url;
            var headers = new List<(string, string)>();
            if (config == null) { Debug.LogError("[CielConversation] 接続の設定（Token Config）がない"); yield break; }
            switch (config.TokenSourceType)
            {
                case TokenSourceType.DevelopmentTokenServer:
                    url = "https://cloud-api.livekit.io/api/v2/sandbox/connection-details";
                    headers.Add(("X-Sandbox-ID", config.TokenServerId));
                    break;
                case TokenSourceType.Endpoint:
                    url = config.EndpointUrl;
                    if (config.EndpointHeaders != null) foreach (var h in config.EndpointHeaders) headers.Add((h.key, h.value));
                    break;
                case TokenSourceType.Literal:
                    done(config.ServerUrl, config.Token);
                    yield break;
                default:
                    yield break;
            }
            var body = string.IsNullOrEmpty(config.RoomName) ? "{}" : $"{{\"room_name\":\"{config.RoomName}\"}}";
            using var req = new UnityEngine.Networking.UnityWebRequest(url, "POST");
            req.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(body));
            req.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            foreach (var (k, v) in headers) if (!string.IsNullOrEmpty(k)) req.SetRequestHeader(k, v);
            yield return req.SendWebRequest();
            if (req.result != UnityEngine.Networking.UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[CielConversation] トークンを取得できない: {req.error} {req.downloadHandler?.text}");
                yield break;
            }
            var d = JsonUtility.FromJson<ConnectionDetailsJson>(req.downloadHandler.text);
            done(d.server_url, d.participant_token);
        }

        /// マイクを入れる・切る（画面のマイクボタン）
        public void SetMicEnabled(bool on)
        {
            if (_busy || _room == null || on == _recording) return;
            StartCoroutine(on ? MicOn() : MicOff());
        }

        /// マイクの機器を選ぶ（null は OS の既定）。録音中なら入れ直す
        public void SelectMic(string guid)
        {
            _micGuid = guid;
            if (guid == null) PlayerPrefs.DeleteKey(MicPrefKey);
            else PlayerPrefs.SetString(MicPrefKey, guid);
            if (_recording && !_busy) StartCoroutine(Restart());
            Changed?.Invoke();

            IEnumerator Restart()
            {
                yield return MicOff();
                yield return MicOn();
            }
        }

        IEnumerator MicOn()
        {
            _busy = true;
            Changed?.Invoke();
            yield return StartRecording();
            if (_recording)
            {
                if (_micTrack == null)
                {
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
                        StopRecording();
                    }
                }
                else
                {
                    ((ILocalTrack)_micTrack).SetMute(false);
                }
            }
            _busy = false;
            Changed?.Invoke();
        }

        IEnumerator MicOff()
        {
            _busy = true;
            if (_micTrack != null) ((ILocalTrack)_micTrack).SetMute(true);
            StopRecording();   // OS のマイク使用中の表示も消える
            _busy = false;
            Changed?.Invoke();
            yield break;
        }

        void StopRecording()
        {
            if (_platformAudio == null || !_recording) return;
            _recording = false;
            try { _platformAudio.StopRecording(); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 録音を止められない: {e.Message}"); }
        }

        // 選んだマイク（無ければ OS の既定）で録音を始める。開けなければ一覧の順に試す。
        // StartRecording は失敗すると例外を投げるので、列挙子を手で進めて受け止める（エラーで再生が一時停止しないように）
        IEnumerator StartRecording()
        {
            _recording = false;
            var tries = new List<(string name, string guid)>();
            if (_micGuid != null) tries.Add((MicDevices.Find(m => m.guid == _micGuid).name, _micGuid));
            tries.Add(("OS の既定", null));
            foreach (var m in MicDevices) if (m.guid != _micGuid) tries.Add(m);

            foreach (var (name, guid) in tries)
            {
                if (guid != null)
                {
                    try { _platformAudio.SetRecordingDevice(guid); }
                    catch (Exception e) { Debug.LogWarning($"[CielConversation] マイク '{name}' を選べない: {e.Message}"); continue; }
                }
                var it = _platformAudio.StartRecording();
                var ok = false;
                while (true)
                {
                    object current;
                    try
                    {
                        if (!it.MoveNext()) { ok = true; break; }
                        current = it.Current;
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning($"[CielConversation] マイク '{name}' を開けない: {e.Message}");
                        break;
                    }
                    yield return current;
                }
                if (ok)
                {
                    _recording = true;
                    Debug.Log($"[CielConversation] マイク '{name}' で録音中");
                    yield break;
                }
            }
            Debug.LogWarning("[CielConversation] 使えるマイクがない");
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
            Trace("声の受信を始めた");
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
            StopRecording();
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
            SetStatus(State.Disconnected);
        }

        void OnApplicationQuit() => _quitting = true;

        void OnDestroy()
        {
            // 終了時は SDK の部品が先に壊れていることがあるので、片付けは OS に任せる（サンプルと同じ）
            if (!_quitting) EndConversation();
        }
    }
}
