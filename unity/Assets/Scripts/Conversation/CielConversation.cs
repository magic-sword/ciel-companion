// シエルとの音声会話（フェーズ1）。LiveKit のルームに入り、会話サーバー（server/agent）の声を再生し、
// その声の大きさで口を動かす。マイクは最初は切っておき、SetMicEnabled（画面のマイクボタン）で入れる。
//
// 流れ：トークンを取得（UnityWebRequest。設定は TokenSourceComponentConfig）→ 端末の音声（WebRTC のエコー除去つき）を用意 → ルームへ接続
//       → 会話サーバーの音声トラックが届いたら、口パク用の音量を測る。
//       マイクを入れると、録音を始めて（初回はトラックを公開）、切ると録音を止めてトラックをミュートする。
// 声の再生は端末の音声（PlatformAudio）が自動で行う。口パク用には同じトラックを Unity の AudioSource でも受け、
// 音量だけ測って音は消す（二重に鳴らさない）。
// 相づち（「うん。」など。server/agent/aizuchi.py）は、シエルの声とは別のトラック（ciel-aizuchi）で届く。
// 同じように音量を測り、口パクは大きいほうに合わせる。
// マイクの機器：PC は OS の一覧から選べる（既定は OS の既定のマイク）。スマホは OS が切り替えを管理するので選ばない。
// 声を出す機器（スピーカー）も PC では選べる。「既定」は、Windows に OS の既定の機器を問い合わせて、その機器を選ぶ（WindowsDefaultAudio）。
// 再生中は出力の機器を変えられないので、シエルの声の受信をいったん止めてから変え、受け直す（SwitchWhilePlaying）。
// 仮想オーディオケーブルへ出せば、Meet・Zoom などの会議にシエルの声を流せる。
// 会話のしかた：おしゃべり度（ひかえめ・ふつう・おしゃべり）と、その場にいる人（自動・ひとり・身近な人・人前）。
// 会話サーバー（server/agent/mode.py）へ、選んだ設定と、声を仮想オーディオケーブル（会議）へ出しているかを、
// つないだとき・会話サーバーが入ってきたとき・設定や声の出力が変わったときに知らせる（topic ciel.style）。
// 実際の答え方・出し方は会話サーバーが決め（自動なら、会議・聞こえた声の数で変わる）、conversation.style で返ってくる。
// シエルの声の大きさ：SetVoiceVolume（設定画面）で、会話サーバー（server/agent/volume.py）へ送る。会話サーバーが声を小さくして送る。
// 会話のまとめ（議事録など）：StartSummary・FinishSummary・RefreshSummary（画面の「まとめ」のパネル）で、会話サーバー（server/agent/minutes.py）へ送る。
// 中身は ciel.summary で分けて届き（Summary）、選べる種類は summary.templates で届く（SummaryTemplates）。
// 参加者：会話サーバー（server/agent/speakers.py）が聞き分けた人と最後に話した人を speakers.state で知らせる（Speakers）。
// 画面からの名前の直しは FixSpeaker で送る（topic ciel.speakers。この会話の間だけ）。
// 開発用のサーバー：SetDevServer（設定画面の開発スイッチ）で、開発用の会話サーバー（ciel-dev、server/compose.dev.yaml）に
// つなぐ部屋にする。トークンを頼むときに「ciel-dev を呼ぶ」部屋の設定（room_config）を添える。本番の会話サーバーはその部屋に入らない。
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
        [SerializeField] CielExpression _expression;
        [Tooltip("接続の設定（Assets/Settings/LiveKitTokenSource.asset）")]
        [SerializeField] TokenSourceComponentConfig _tokenConfig;
        [SerializeField] bool _connectOnStart = true;
        [Tooltip("口の開きの倍率（声の大きさ → 口の開き）")]
        [SerializeField] float _mouthGain = 6f;
        [Tooltip("口が開くときと閉じるときのなめらかさ（秒）")]
        [SerializeField] float _openTime = 0.04f, _closeTime = 0.10f;

        const string MicPrefKey = "ciel.micDevice";
        const string SpeakerPrefKey = "ciel.speakerDevice";
        const string ModePrefKey = "ciel.conversationMode";   // 以前の設定（2 人・多人数）。新しい設定へ移す
        const string TalkPrefKey = "ciel.talk";
        const string PresencePrefKey = "ciel.presence";
        const string SpeakerphonePrefKey = "ciel.speakerphone";
        const string VolumePrefKey = "ciel.voiceVolume";
        const string DevServerPrefKey = "ciel.devServer";
        const string DevAgentName = "ciel-dev";   // 開発用の会話サーバーの名前（server/compose.dev.yaml の CIEL_AGENT_NAME）
        const string AizuchiTrack = "ciel-aizuchi";   // 相づちのトラックの名前（server/agent/aizuchi.py の TRACK）

        [Tooltip("この文字を名前に含む「声の出力」は会議へつなぐ仮想オーディオケーブルとみなす（自動のとき多人数にする）")]
        [SerializeField] string[] _meetingOutputKeywords = { "CABLE", "VB-Audio", "Voicemeeter" };

        Room _room;
        PlatformAudio _platformAudio;
        PlatformAudioSource _micSource;
        LocalAudioTrack _micTrack;
        AudioStream _voiceStream;
        RemoteTrackPublication _voicePublication;   // シエルの声（受け直すときに使う）
        bool _restartingPlayout;
        AgentVoiceMeter _meter;
        AudioStream _aizuchiStream;   // 相づちのトラック（口パク用に音量を測る）
        RemoteTrackPublication _aizuchiPublication;
        AgentVoiceMeter _aizuchiMeter;
        bool _recording, _busy, _quitting, _micRestarting;
        int? _sleepTimeoutBeforeMinutes;
        bool _applicationPaused;
        string _micGuid;   // 選んだマイク。null は OS の既定
        string _speakerGuid;   // 選んだスピーカー。null は OS の既定

        public enum State { Disconnected, Connecting, Connected, Failed }
        public State Status { get; private set; } = State.Disconnected;
        public bool MicEnabled => _recording;
        public bool MicBusy => _busy;
        /// 自分の声が会話サーバーに届いているか（LiveKit の「話している人」の知らせで変わる。0.3〜0.5 秒ほど遅れる）
        public bool UserSpeaking => _userSpeaking && _recording;
        bool _userSpeaking;
        /// 会話サーバーが会議の議事録をとっているか（会話サーバーの知らせ minutes.state で変わる）
        public bool MinutesOn { get; private set; }
        [Serializable]
        public sealed class ResearchSource
        {
            public int number;
            public string title, url;
        }
        public sealed class ResearchResult
        {
            public int id;
            public string question, checkedAt, status;
            public bool clipped;
            public string[] parts;
            public float startedAt;   // 調べ始めの知らせが届いた時刻（Time.unscaledTime。調べている秒数を出す）
            public readonly List<ResearchSource> sources = new List<ResearchSource>();
            public string Summary => parts == null ? "" : string.Concat(parts);
        }
        [Serializable]
        sealed class ResearchPacket
        {
            public string type, question, checked_at, status, text;
            public int id, part_count, part;
            public bool clipped;
            public ResearchSource source;
        }
        readonly List<ResearchResult> _researchResults = new List<ResearchResult>();
        public IReadOnlyList<ResearchResult> ResearchResults => _researchResults;
        public int ResearchRevision { get; private set; }

        /// シエルが声で聞き分けた人（会話サーバーの speakers.state）
        [Serializable]
        public sealed class Speaker
        {
            public string id, name;
            public bool named, remembered;
        }
        [Serializable]
        sealed class SpeakersPacket
        {
            public Speaker[] speakers;
            public string speaking, correctable;
            public bool speaking_sure;
            public int heard;
        }
        [Serializable]
        sealed class SpeakerFix
        {
            public int v = 1;
            public string type = "speakers.control", action, speaker_id, name, into;
        }
        /// 会話のまとめ（議事録など。会話サーバーの minutes.py が ciel.summary で分けて送る）
        [Serializable]
        public sealed class SummarySource
        {
            public string title, url;
        }
        [Serializable]
        public sealed class SummaryItem
        {
            public string id, text, who, due, status;
            public int rev;
            public bool done;
            public string[] points;
            public SummarySource[] sources;
        }
        [Serializable]
        public sealed class SummarySection
        {
            public string id, label, kind;
            public SummaryItem[] items;
        }
        [Serializable]
        public sealed class SummaryState
        {
            public string meeting_id, stage, template, label, title, summary, current_topic;
            public bool recording, updating;   // updating：ライブの差分を作っている最中
            public double started_at, updated_at;
            public int pending_turns, rev;
            public string[] attendees;
            public SummarySection[] sections;
        }
        [Serializable]
        public sealed class SummaryTemplate
        {
            public string name, label, description;
        }
        [Serializable]
        sealed class SummaryPart
        {
            public string text;
            public int seq, part, parts;
        }
        [Serializable]
        sealed class TemplatesPacket
        {
            public SummaryTemplate[] templates;
        }
        /// 今のまとめ（とっていないときは、直近に終えたもの。まだ無ければ null）
        public SummaryState Summary { get; private set; }
        public int SummaryRevision { get; private set; }
        /// まとめを作っている（とっている途中のライブの更新か、終えたあとの清書）
        public bool Summarizing => Summary != null && (Summary.updating || Summary.stage == "queued" || Summary.stage == "building");
        /// Web で調べている（調べた記録のうち、まだ終わっていないものがある）
        public bool ResearchPending => _researchResults.Exists(r => r.status == "pending");
        /// いちばん前から調べているものの、調べ始めてからの秒数（調べていなければ -1）
        public float ResearchSeconds
        {
            get
            {
                var first = -1f;
                foreach (var r in _researchResults)
                    if (r.status == "pending" && (first < 0 || r.startedAt < first)) first = r.startedAt;
                return first < 0 ? -1f : Time.unscaledTime - first;
            }
        }
        /// 選べるまとめの種類（会話サーバーが会話の始めに送る）
        public IReadOnlyList<SummaryTemplate> SummaryTemplates => _summaryTemplates;
        readonly List<SummaryTemplate> _summaryTemplates = new List<SummaryTemplate>();
        int _summarySeq = -1;
        string[] _summaryParts;

        readonly List<Speaker> _speakers = new List<Speaker>();
        public IReadOnlyList<Speaker> Speakers => _speakers;
        /// 最後に話したと判定した人と、そのときの時刻（Time.unscaledTime）。名前の札を少しのあいだ光らせる
        public string SpeakingId { get; private set; } = "";
        public bool SpeakingSure { get; private set; }
        public float SpeakingAt { get; private set; } = -1f;
        /// 「さっきの発言はこの人じゃない」と直せる人（直前の発言者）
        public string CorrectableId { get; private set; } = "";
        public int SpeakersRevision { get; private set; }
        int _heard = -1;

        public static bool IsWebUrl(string value) => Uri.TryCreate(value, UriKind.Absolute, out var uri)
            && (uri.Scheme == "https" || uri.Scheme == "http") && string.IsNullOrEmpty(uri.UserInfo);
        /// 状態が変わったとき（画面の表示の更新用）
        public event Action Changed;

        /// PC ならマイクの一覧（名前、ID）。スマホは空（OS に任せる）
        public List<(string name, string guid)> MicDevices { get; } = new List<(string, string)>();
        public bool CanSelectMic => Application.isMobilePlatform == false && MicDevices.Count > 0;
        public string SelectedMic => _micGuid;

        /// PC ならスピーカーの一覧（名前、ID）。スマホは空（OS に任せる）
        public List<(string name, string guid)> SpeakerDevices { get; } = new List<(string, string)>();
        public bool CanSelectSpeaker => Application.isMobilePlatform == false && SpeakerDevices.Count > 0;

        /// Android：声を本体のスピーカーから出すか（オフは受話口。耳に当てて聞く）。既定はオン（画面のシエルを見ながら話すので）
        public bool CanUseSpeakerphone => Application.platform == RuntimePlatform.Android;
        public bool SpeakerphoneOn { get; private set; } = true;
        public string SelectedSpeaker => _speakerGuid;

        /// おしゃべり度：ひかえめ（呼ばれたら答える）・ふつう（いつも答える）・おしゃべり（自分からも話しかける）
        public enum Talk { Quiet, Normal, Chatty }
        /// その場にいる人（覚えていることの出し方）：自動・ひとり・身近な人・人前
        public enum Presence { Auto, Solo, Close, Public }
        public Talk TalkChoice { get; private set; } = Talk.Normal;
        public Presence PresenceChoice { get; private set; } = Presence.Auto;
        Talk? _serverTalk;
        Presence? _serverPresence;
        /// いまの答え方。会話サーバーが決めたもの（つなぐ前は、選んだ設定と声の出力から決める）
        public Talk CurrentTalk => _serverTalk ?? (IsMeetingOutput() && PresenceChoice == Presence.Auto ? Talk.Quiet : TalkChoice);
        /// いまの覚えていることの出し方（Auto にはならない）
        public Presence CurrentPresence => _serverPresence
            ?? (PresenceChoice != Presence.Auto ? PresenceChoice : IsMeetingOutput() ? Presence.Public : Presence.Solo);
        /// 自動で決めた理由（"meeting"：会議につないでいる、"voices"：2 人以上の声が聞こえた、""：なし）
        public string PresenceReason { get; private set; } = "";

        /// シエルの声の大きさ（0〜1。1 がそのまま）。端末の音量とは別
        public float VoiceVolume { get; private set; } = 1f;
        bool _volumeDirty;
        float _volumeSentAt = -1f;

        /// いまのシエルの声の大きさ（0〜1 くらい。画面の波形用）。声の大きさの設定に左右されない
        public float VoiceLevel => Mathf.Max(_meter != null ? _meter.Level : 0f, _aizuchiMeter != null ? _aizuchiMeter.Level : 0f)
                                   / Mathf.Max(VoiceVolume, 0.05f);
        bool IsMeetingOutput()
        {
            if (_speakerGuid == null) return false;
            var name = SpeakerDevices.Find(m => m.guid == _speakerGuid).name ?? "";
            foreach (var k in _meetingOutputKeywords)
                if (!string.IsNullOrEmpty(k) && name.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0) return true;
            return false;
        }

        void Start()
        {
            if (_mouth != null) _mouth.BlendMode = Live2D.Cubism.Framework.CubismParameterBlendMode.Override;
            _micGuid = PlayerPrefs.HasKey(MicPrefKey) ? PlayerPrefs.GetString(MicPrefKey) : null;
            _speakerGuid = PlayerPrefs.HasKey(SpeakerPrefKey) ? PlayerPrefs.GetString(SpeakerPrefKey) : null;
            if (!PlayerPrefs.HasKey(TalkPrefKey) && PlayerPrefs.GetInt(ModePrefKey, 0) == 2)
                PlayerPrefs.SetInt(TalkPrefKey, (int)Talk.Quiet);   // 以前「多人数」を選んでいた人は、ひかえめから始める
            TalkChoice = (Talk)Mathf.Clamp(PlayerPrefs.GetInt(TalkPrefKey, (int)Talk.Normal), 0, 2);
            PresenceChoice = (Presence)Mathf.Clamp(PlayerPrefs.GetInt(PresencePrefKey, (int)Presence.Auto), 0, 3);
            SpeakerphoneOn = PlayerPrefs.GetInt(SpeakerphonePrefKey, 1) == 1;
            VoiceVolume = Mathf.Clamp01(PlayerPrefs.GetFloat(VolumePrefKey, 1f));
            DevServer = PlayerPrefs.GetInt(DevServerPrefKey, 0) == 1;
            if (_connectOnStart) StartConversation();
        }

        /// 返事を考えているか（会話サーバーの agent.thinking を受けてから、声が出るまで。6 秒で消える）
        public bool Thinking => Status == State.Connected && _thinkingSince >= 0f && Time.unscaledTime - _thinkingSince < ThinkingTimeout
                                && AgentState != "speaking";
        float _thinkingSince = -1f;
        const float ThinkingTimeout = 6f;

        /// 会話サーバーのいまの様子（LiveKit Agents が参加者の属性 lk.agent.state で知らせる）：
        /// listening（聞いている）・speaking（話している）など。つないでいなければ空。Realtime API と自前の読み上げの組み合わせでは
        /// thinking を通らないので、考えている間は Thinking（会話サーバーの agent.thinking）で見る
        public string AgentState { get; private set; } = "";
        const string AgentStateAttribute = "lk.agent.state";

        /// 開発用の会話サーバーにつなぐか（設定画面の開発スイッチ）
        public bool DevServer { get; private set; }
        bool _restartAfterConnect;   // つないでいる途中で切り替えられた。つながったら、つなぎ直す

        /// 開発用の会話サーバーにつなぐ・本番に戻す。会話は別の部屋になるので、つないでいたらつなぎ直す
        public void SetDevServer(bool on)
        {
            if (on == DevServer) return;
            DevServer = on;
            PlayerPrefs.SetInt(DevServerPrefKey, on ? 1 : 0);
            PlayerPrefs.Save();
            if (Status == State.Connected || Status == State.Failed)
            {
                EndConversation();
                StartConversation();
            }
            else if (Status == State.Connecting) _restartAfterConnect = true;
            Changed?.Invoke();
        }

        public void StartConversation()
        {
            if (_room == null && Status != State.Connecting) StartCoroutine(Connect());
        }

        void SetStatus(State s)
        {
            Status = s;
            UpdateMinutesSleep();
            Changed?.Invoke();
        }

        void SetMinutesRecording(bool recording)
        {
            MinutesOn = recording;
            UpdateMinutesSleep();
        }

        // 記録がサーバーで始まった間だけ画面の自動消灯を防ぐ。重複通知では元の値を上書きしない。
        void UpdateMinutesSleep()
        {
            if (MinutesOn && Status == State.Connected && isActiveAndEnabled && !_applicationPaused && !_quitting)
            {
                if (!_sleepTimeoutBeforeMinutes.HasValue)
                    _sleepTimeoutBeforeMinutes = Screen.sleepTimeout;
                Screen.sleepTimeout = SleepTimeout.NeverSleep;
            }
            else
                RestoreMinutesSleep();
        }

        void RestoreMinutesSleep()
        {
            if (!_sleepTimeoutBeforeMinutes.HasValue) return;
            // 別の機能が設定を変更していた場合は、その値を尊重する。
            if (Screen.sleepTimeout == SleepTimeout.NeverSleep)
                Screen.sleepTimeout = _sleepTimeoutBeforeMinutes.Value;
            _sleepTimeoutBeforeMinutes = null;
        }

        void OnEnable() => UpdateMinutesSleep();
        void OnDisable() => RestoreMinutesSleep();

        void OnApplicationPause(bool paused)
        {
            _applicationPaused = paused;
            UpdateMinutesSleep();
        }

        void OnRoomDisconnected(Room room)
        {
            if (room != _room) return;
            _userSpeaking = false;
            SetMinutesRecording(false);
            Changed?.Invoke();
        }

        void OnActiveSpeakersChanged(List<Participant> speakers)
        {
            var me = _room?.LocalParticipant?.Identity;
            _userSpeaking = me != null && speakers.Exists(p => p != null && p.Identity == me);
        }

        static void Trace(string what) =>
            Debug.Log($"[CielConversation] {what}（frame={Time.frameCount}, t={Time.realtimeSinceStartup:0.00}）");

        IEnumerator Connect()
        {
            _restartAfterConnect = false;
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
                    Debug.Log($"[CielConversation] マイク {d.Index}: {d.Name} [{d.Guid}]");
                    if (!string.IsNullOrEmpty(d.Guid)) MicDevices.Add((d.Name, d.Guid));
                }
                SpeakerDevices.Clear();
                foreach (var d in play)
                {
                    Debug.Log($"[CielConversation] スピーカー {d.Index}: {d.Name} [{d.Guid}]");
                    if (!string.IsNullOrEmpty(d.Guid)) SpeakerDevices.Add((d.Name, d.Guid));
                }
                // 保存していた機器が今は無いなら、既定に戻す
                if (_micGuid != null && !MicDevices.Exists(m => m.guid == _micGuid)) _micGuid = null;
                if (_speakerGuid != null && !SpeakerDevices.Exists(m => m.guid == _speakerGuid)) _speakerGuid = null;
                Debug.Log($"[CielConversation] OS の既定：マイク [{WindowsDefaultAudio.Mic()}]、スピーカー [{WindowsDefaultAudio.Speaker()}]");
                ApplySpeaker();
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
            _room.DataReceived += OnDataReceived;
            _room.ParticipantConnected += OnParticipantConnected;
            _room.ParticipantAttributesChanged += OnParticipantAttributesChanged;
            _room.Disconnected += OnRoomDisconnected;
            _room.ActiveSpeakersChanged += OnActiveSpeakersChanged;
            Trace("ルームへ接続");
            yield return _room.Connect(serverUrl, token, new RoomOptions());
            Debug.Log($"[CielConversation] ルーム '{_room.Name}' に接続した（マイクは切ってある）");
            // 接続のときに WebRTC が声の出力を OS の既定（通話用の機器）へ戻すので、選んだ機器をかけ直す。
            // 会話サーバーの声が届いて再生が始まる前なら、ここで切り替わる
            ApplySpeaker();
            ApplySpeakerphone();
            SetMinutesRecording(false);   // 会話サーバーは部屋ごとに新しく入るので、議事録はとっていない
            SetStatus(State.Connected);
            if (_restartAfterConnect)
            {
                // つないでいる途中で、本番・開発用が切り替えられた。選ばれたほうの部屋につなぎ直す
                EndConversation();
                StartConversation();
                yield break;
            }
            SendStyle();
            SendVolume();
        }

        [System.Serializable]
        class ConnectionDetailsJson
        {
            public string server_url;
            public string participant_token;
        }

        [Serializable] class TokenVideoGrant { public string room; }
        [Serializable] class TokenClaims { public TokenVideoGrant video; }

        // 署名の検証は接続先の LiveKit が行う。ここでは取得先が指定した部屋を守ったか確認する。
        static bool IsTokenForRoom(string token, string roomName)
        {
            if (string.IsNullOrEmpty(token)) return false;
            var parts = token.Split('.');
            if (parts.Length != 3) return false;
            try
            {
                var payload = parts[1].Replace('-', '+').Replace('_', '/');
                payload = payload.PadRight((payload.Length + 3) / 4 * 4, '=');
                var json = System.Text.Encoding.UTF8.GetString(Convert.FromBase64String(payload));
                return JsonUtility.FromJson<TokenClaims>(json)?.video?.room == roomName;
            }
            catch (Exception) { return false; }
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
                    Debug.LogError("[CielConversation] 接続ごとに別の部屋が必要です。トークン取得先を DevelopmentTokenServer または Endpoint に設定してください。");
                    yield break;
                default:
                    yield break;
            }
            // 接続ごとに独立した会話にする。端末名・利用者名は部屋名に入れない。
            var roomName = "ciel-" + Guid.NewGuid().ToString("N");
            // 開発用のサーバーにつなぐときは、その部屋に開発用の会話サーバーを呼ぶ（LiveKit の部屋の設定 room_config）
            var roomConfig = DevServer ? $",\"room_config\":{{\"agents\":[{{\"agent_name\":\"{DevAgentName}\"}}]}}" : "";
            var body = $"{{\"room_name\":\"{roomName}\"{roomConfig}}}";
            using var req = new UnityEngine.Networking.UnityWebRequest(url, "POST");
            req.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(body));
            req.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            foreach (var (k, v) in headers) if (!string.IsNullOrEmpty(k)) req.SetRequestHeader(k, v);
            yield return req.SendWebRequest();
            if (req.result != UnityEngine.Networking.UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[CielConversation] トークンを取得できない: {req.error}");
                yield break;
            }
            var d = JsonUtility.FromJson<ConnectionDetailsJson>(req.downloadHandler.text);
            if (d == null || string.IsNullOrEmpty(d.server_url) || !IsTokenForRoom(d.participant_token, roomName))
            {
                Debug.LogError("[CielConversation] 指定した部屋のトークンを取得できません。取得先の room_name 対応を確認してください。");
                yield break;
            }
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
            if (_recording || _busy) StartCoroutine(Restart());
            Changed?.Invoke();

            // 入れる・切るの途中なら、終わるのを待ってから入れ直す（待たずにやめると、あとで選んだ機器が使われない）
            IEnumerator Restart()
            {
                while (_busy) yield return null;
                if (!_recording || _micRestarting) yield break;
                _micRestarting = true;
                yield return MicOff();
                yield return MicOn();
                _micRestarting = false;
            }
        }

        /// 声を出す機器を選ぶ（null は OS の既定）。会話中でもすぐ切り替える
        public void SelectSpeaker(string guid)
        {
            _speakerGuid = guid;
            if (guid == null) PlayerPrefs.DeleteKey(SpeakerPrefKey);
            else PlayerPrefs.SetString(SpeakerPrefKey, guid);
            if (_platformAudio != null) ApplySpeaker();
            SendStyle();   // 自動のときは、声の出力（会議かどうか）で変わる
            Changed?.Invoke();
        }

        /// Android：声を本体のスピーカーから出す・受話口から出す
        public void SetSpeakerphone(bool on)
        {
            SpeakerphoneOn = on;
            PlayerPrefs.SetInt(SpeakerphonePrefKey, on ? 1 : 0);
            ApplySpeakerphone();
            Changed?.Invoke();
        }

        // LiveKit が通話用の音声の設定にしたあと（接続・録音の開始・声の受信の開始）にも、かけ直す
        void ApplySpeakerphone()
        {
            if (!CanUseSpeakerphone) return;
            var ok = AndroidSpeaker.Set(SpeakerphoneOn);
            Debug.Log($"[CielConversation] 声の出力：{(SpeakerphoneOn ? "スピーカー" : "受話口")}{(ok ? "" : "（切り替えられなかった）")}");
        }

        /// おしゃべり度を選ぶ
        public void SelectTalk(Talk choice)
        {
            TalkChoice = choice;
            PlayerPrefs.SetInt(TalkPrefKey, (int)choice);
            _serverTalk = null;   // 会話サーバーの返事が来るまでは、選んだ設定で表示する
            SendStyle();
            Changed?.Invoke();
        }

        /// その場にいる人を選ぶ
        public void SelectPresence(Presence choice)
        {
            PresenceChoice = choice;
            PlayerPrefs.SetInt(PresencePrefKey, (int)choice);
            _serverTalk = null;
            _serverPresence = null;
            SendStyle();
            Changed?.Invoke();
        }

        static readonly string[] TalkNames = { "quiet", "normal", "chatty" };
        static readonly string[] PresenceNames = { "auto", "solo", "close", "public" };

        // 同じ設定を何度送ってもよい（会話サーバーは変わったときだけ切り替える）
        void SendStyle()
        {
            if (_room == null || Status != State.Connected) return;
            var talk = TalkNames[(int)TalkChoice];
            var presence = PresenceNames[(int)PresenceChoice];
            var meeting = IsMeetingOutput() ? "true" : "false";
            var json = $"{{\"v\":1,\"type\":\"conversation.style\",\"talk\":\"{talk}\",\"presence\":\"{presence}\",\"meeting\":{meeting}}}";
            try
            {
                _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.style");
                Debug.Log($"[CielConversation] 会話のしかた {talk}・{presence}（会議 {meeting}）を送った");
            }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 会話のしかたを送れない: {e.Message}"); }
        }

        // 会話サーバーが後から部屋に入っても、今のモードが伝わるように送り直す
        void OnParticipantConnected(Participant participant)
        {
            SendStyle();
            SendVolume();
        }

        // 会話サーバーの様子が変わったら、画面に知らせる（考えている間を「考えています…」と見せる）
        void OnParticipantAttributesChanged(Participant participant)
        {
            if (participant == null || participant.Attributes == null) return;
            if (!participant.Attributes.TryGetValue(AgentStateAttribute, out var state) || state == AgentState) return;
            AgentState = state;
            if (state == "speaking") _thinkingSince = -1f;   // 声が出たので、考え終わった
            Changed?.Invoke();
        }

        /// シエルの声の大きさを変える（0〜1）。つまみを動かしているあいだは、送るのを間引く
        public void SetVoiceVolume(float volume)
        {
            volume = Mathf.Clamp01(volume);
            if (Mathf.Approximately(volume, VoiceVolume)) return;
            VoiceVolume = volume;
            PlayerPrefs.SetFloat(VolumePrefKey, volume);
            _volumeDirty = true;
            Changed?.Invoke();
        }

        // 同じ大きさを何度送ってもよい
        void SendVolume()
        {
            _volumeDirty = false;
            _volumeSentAt = Time.realtimeSinceStartup;
            if (_room == null || Status != State.Connected) return;
            var json = $"{{\"v\":1,\"type\":\"voice.volume\",\"volume\":{VoiceVolume.ToString("0.###", System.Globalization.CultureInfo.InvariantCulture)}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.volume"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 声の大きさを送れない: {e.Message}"); }
        }

        // 既定（null）は OS の既定の機器を選ぶ（空の ID を渡すと、一覧の最初の機器になってしまう）。スマホは OS に任せる
        void ApplySpeaker()
        {
            if (_platformAudio == null || Application.isMobilePlatform) return;
            var guid = _speakerGuid ?? DefaultDevice(WindowsDefaultAudio.Speaker(), SpeakerDevices);
            var name = SpeakerDevices.Find(m => m.guid == guid).name ?? "一覧の最初の機器";
            if ((_voicePublication != null && _voiceStream != null) || _aizuchiStream != null)
            {
                _pendingSpeaker = (guid, name);   // 切り替えの途中で選び直したら、最後に選んだ機器にする
                if (!_restartingPlayout) StartCoroutine(SwitchWhilePlaying(_voicePublication, _aizuchiPublication));
                return;
            }
            TrySetSpeaker(guid, name, warn: true);
        }

        (string guid, string name) _pendingSpeaker;

        bool TrySetSpeaker(string guid, string name, bool warn)
        {
            try
            {
                _platformAudio.SetPlayoutDevice(guid ?? "");
                Debug.Log($"[CielConversation] スピーカー '{name}'{(_speakerGuid == null ? "（OS の既定）" : "")} で再生");
                return true;
            }
            catch (Exception e)
            {
                if (warn) Debug.LogWarning($"[CielConversation] スピーカー '{name}' を選べない: {e.Message}");
                return false;
            }
        }

        // OS の既定の機器が一覧にあれば、その ID（無ければ null）
        static string DefaultDevice(string id, List<(string name, string guid)> devices) =>
            id != null && devices.Exists(m => string.Equals(m.guid, id, StringComparison.OrdinalIgnoreCase))
                ? devices.Find(m => string.Equals(m.guid, id, StringComparison.OrdinalIgnoreCase)).guid : null;

        // Windows の端末の音声（WebRTC）は、再生しているあいだは出力の機器を変えられない（"Device not found" のエラーになる）。
        // シエルの声の受信をいったん止めて再生を止め、機器を変えてから受け直す（声が一瞬途切れる）
        IEnumerator SwitchWhilePlaying(RemoteTrackPublication publication, RemoteTrackPublication aizuchi)
        {
            _restartingPlayout = true;
            Trace("スピーカーを変えるので、シエルの声の受信をいったん止める");
            publication?.SetSubscribed(false);
            aizuchi?.SetSubscribed(false);   // 相づちのトラックも鳴っていると、機器を変えられない
            // 受信が止まる（TrackUnsubscribed で _voiceStream が片付く）のを待つ。来なくても 2 秒で先へ進む
            var until = Time.realtimeSinceStartup + 2f;
            while ((_voiceStream != null || _aizuchiStream != null) && Time.realtimeSinceStartup < until) yield return null;
            // 再生が止まるまで少しかかることがあるので、1 秒のあいだ選び直す
            var ok = false;
            until = Time.realtimeSinceStartup + 1f;
            while (!(ok = TrySetSpeaker(_pendingSpeaker.guid, _pendingSpeaker.name, warn: false)) && Time.realtimeSinceStartup < until)
                yield return null;
            if (!ok) TrySetSpeaker(_pendingSpeaker.guid, _pendingSpeaker.name, warn: true);
            publication?.SetSubscribed(true);   // 受け直す（OnTrackSubscribed で口パク用の受信も作り直す）
            aizuchi?.SetSubscribed(true);
            _restartingPlayout = false;
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
            // OS の既定：PC は Windows に問い合わせた機器を選ぶ（選ばないと、前に選んだ機器のまま録音する）
            tries.Add(("OS の既定", Application.isMobilePlatform ? null : DefaultDevice(WindowsDefaultAudio.Mic(), MicDevices)));
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
                    ApplySpeakerphone();   // 録音を始めると、通話の設定で受話口へ戻ることがある
                    Debug.Log($"[CielConversation] マイク '{name}' で録音中");
                    yield break;
                }
            }
            Debug.LogWarning("[CielConversation] 使えるマイクがない");
        }

        void OnTrackSubscribed(IRemoteTrack track, RemoteTrackPublication publication, RemoteParticipant participant)
        {
            if (!(track is RemoteAudioTrack audio)) return;
            if (publication.Name == AizuchiTrack)
            {
                if (_aizuchiStream != null) return;
                _aizuchiPublication = publication;
                _aizuchiMeter = CreateMeter("CielAizuchiMeter", audio, out _aizuchiStream);
                Debug.Log($"[CielConversation] {participant.Identity} の相づちを受信");
                return;
            }
            if (_voiceStream != null) return;
            _voicePublication = publication;
            _meter = CreateMeter("CielVoiceMeter", audio, out _voiceStream);
            Trace("声の受信を始めた");
            ApplySpeakerphone();
            Debug.Log($"[CielConversation] {participant.Identity} の声を受信");
        }

        // 口パク用：音量だけを測る AudioSource（音は AgentVoiceMeter が消す）
        AgentVoiceMeter CreateMeter(string name, RemoteAudioTrack audio, out AudioStream stream)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            var source = go.AddComponent<AudioSource>();
            stream = new AudioStream(audio, source);
            return go.AddComponent<AgentVoiceMeter>();   // AudioStream の後に付けて、届いた音を読む
        }

        [Serializable]
        class EventJson
        {
            public int v;
            public string type;
            public int seq;
            public string expression;
            public float intensity;
            public int ttl_ms;
            public bool recording;   // minutes.state
            public string talk, presence, reason;   // conversation.style
            public bool on;   // agent.thinking
            public string meeting_id;   // summary.progress
            public int pending_turns;
            public bool updating;
        }

        // 会話サーバーのイベント（仕様書 6 章）。表情（character.expression）と、議事録をとっているか（minutes.state）
        void OnDataReceived(byte[] data, Participant participant, DataPacketKind kind, string topic)
        {
            if (topic == "ciel.research")
            {
                OnResearchData(data);
                return;
            }
            if (topic == "ciel.summary")
            {
                OnSummaryPart(data);
                return;
            }
            if (topic != "ciel.event") return;
            EventJson e;
            try { e = JsonUtility.FromJson<EventJson>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] イベントを読めない: {ex.Message}"); return; }
            if (e.type == "character.expression" && _expression != null)
            {
                _expression.Set(e.expression, e.ttl_ms / 1000f);
                Debug.Log($"[CielConversation] 表情 {e.expression}（{e.ttl_ms} ms）");
            }
            else if (e.type == "conversation.style")
            {
                var t = Array.IndexOf(TalkNames, e.talk);
                var p = Array.IndexOf(PresenceNames, e.presence);
                if (t >= 0) _serverTalk = (Talk)t;
                if (p > 0) _serverPresence = (Presence)p;
                PresenceReason = e.reason ?? "";
                Debug.Log($"[CielConversation] いまの会話のしかた：{e.talk}・{e.presence}{(PresenceReason != "" ? $"（{PresenceReason}）" : "")}");
                Changed?.Invoke();
            }
            else if (e.type == "agent.thinking")
            {
                // 返事を頼んだ（on）・取り消された（off）。声が出たら（AgentState が speaking）消える
                _thinkingSince = e.on ? Time.unscaledTime : -1f;
                Changed?.Invoke();
            }
            else if (e.type == "minutes.state")
            {
                SetMinutesRecording(e.recording);
                Debug.Log($"[CielConversation] 議事録：{(e.recording ? "とっている" : "とっていない")}");
                Changed?.Invoke();
            }
            else if (e.type == "speakers.state")
                OnSpeakers(data);
            else if (e.type == "summary.progress" && Summary != null && Summary.meeting_id == e.meeting_id)
            {
                Summary.pending_turns = e.pending_turns;
                Summary.updating = e.updating;
                Changed?.Invoke();
            }
            else if (e.type == "summary.templates")
            {
                TemplatesPacket p;
                try { p = JsonUtility.FromJson<TemplatesPacket>(System.Text.Encoding.UTF8.GetString(data)); }
                catch (Exception) { return; }
                if (p?.templates == null || p.templates.Length > 20) return;
                _summaryTemplates.Clear();
                foreach (var t in p.templates)
                    if (t != null && !string.IsNullOrEmpty(t.name) && !string.IsNullOrEmpty(t.label)) _summaryTemplates.Add(t);
                Changed?.Invoke();
            }
        }

        // まとめの中身は分けて届く。seq ごとに parts 個そろったら、つないで読む（古い seq の残りは捨てる）
        void OnSummaryPart(byte[] data)
        {
            SummaryPart p;
            try { p = JsonUtility.FromJson<SummaryPart>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception) { return; }
            if (p == null || p.parts <= 0 || p.parts > 64 || p.part < 0 || p.part >= p.parts || (p.text?.Length ?? 0) > 4000) return;
            if (p.seq != _summarySeq || _summaryParts == null || _summaryParts.Length != p.parts)
            {
                _summarySeq = p.seq;
                _summaryParts = new string[p.parts];
            }
            _summaryParts[p.part] = p.text ?? "";
            if (Array.IndexOf(_summaryParts, null) >= 0) return;
            SummaryState s;
            try { s = JsonUtility.FromJson<SummaryState>(string.Concat(_summaryParts)); }
            catch (Exception ex) { Debug.LogWarning($"[CielConversation] まとめを読めない: {ex.Message}"); return; }
            _summaryParts = null;
            if (s?.sections == null || s.sections.Length > 20) return;
            Summary = s;
            SummaryRevision++;
            Changed?.Invoke();
        }

        /// まとめをとり始める（template は SummaryTemplates の name）・終えて下書きを送る・今すぐ更新する
        public void StartSummary(string template) => SendMinutes($"{{\"v\":1,\"type\":\"minutes.control\",\"action\":\"start\",\"template\":{JsonString(template)}}}");
        public void FinishSummary() => SendMinutes("{\"v\":1,\"type\":\"minutes.control\",\"action\":\"finish\"}");
        public void RefreshSummary() => SendMinutes("{\"v\":1,\"type\":\"minutes.control\",\"action\":\"refresh\"}");

        static string JsonString(string s) => "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

        void SendMinutes(string json)
        {
            if (_room == null || Status != State.Connected) return;
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.minutes"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] まとめの操作を送れない: {e.Message}"); }
        }

        void OnSpeakers(byte[] data)
        {
            SpeakersPacket p;
            try { p = JsonUtility.FromJson<SpeakersPacket>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception) { return; }
            if (p?.speakers == null || p.speakers.Length > 64) return;
            _speakers.Clear();
            foreach (var s in p.speakers)
                if (s != null && !string.IsNullOrEmpty(s.id) && !string.IsNullOrEmpty(s.name) && s.name.Length <= 100) _speakers.Add(s);
            if (p.heard != _heard && !string.IsNullOrEmpty(p.speaking)) SpeakingAt = Time.unscaledTime;
            _heard = p.heard;
            SpeakingId = p.speaking ?? "";
            SpeakingSure = p.speaking_sure;
            CorrectableId = p.correctable ?? "";
            SpeakersRevision++;
            Changed?.Invoke();
        }

        /// 参加者パネルからの直し（会話サーバーの speakers.py。この会話の間だけで、声や名前は保存しない）。
        /// action：name（名前を付ける・直す）・merge（into の人と同じ人）・split（さっきの発言はこの人じゃない）
        public void FixSpeaker(string action, string speakerId, string name = null, string into = null)
        {
            if (_room == null || Status != State.Connected) return;
            var json = JsonUtility.ToJson(new SpeakerFix { action = action, speaker_id = speakerId, name = name, into = into });
            try
            {
                _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.speakers");
                Debug.Log($"[CielConversation] 参加者の直し {action} を送った");
            }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] 参加者の直しを送れない: {e.Message}"); }
        }

        void OnResearchData(byte[] data)
        {
            ResearchPacket p;
            try { p = JsonUtility.FromJson<ResearchPacket>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception) { return; }
            if (p == null || p.id <= 0) return;
            var r = _researchResults.Find(x => x.id == p.id);
            if (p.type == "research.result")
            {
                if (p.part_count < 0 || p.part_count > 4 || (p.question?.Length ?? 0) > 1200) return;
                var startedAt = r?.startedAt ?? Time.unscaledTime;   // 結果が届いても、調べ始めの時刻は変えない
                if (r != null) _researchResults.Remove(r);
                r = new ResearchResult { id = p.id, question = p.question, checkedAt = p.checked_at,
                    status = p.status, clipped = p.clipped, parts = new string[p.part_count], startedAt = startedAt };
                _researchResults.Add(r);
                if (_researchResults.Count > 20) _researchResults.RemoveAt(0);
            }
            else if (r != null && p.type == "research.text" && p.part >= 0 && p.part < r.parts.Length)
            {
                if ((p.text?.Length ?? 0) <= 3000) r.parts[p.part] = p.text;
            }
            else if (r != null && p.type == "research.source" && p.source != null)
            {
                if (r.sources.Count < 8 && p.source.number > 0 && p.source.number <= 8
                    && (p.source.title?.Length ?? 0) <= 400 && (p.source.url?.Length ?? 0) <= 3000
                    && IsWebUrl(p.source.url)) r.sources.Add(p.source);
            }
            else if (r != null && p.type == "research.complete")
            {
                ResearchRevision++;
                Changed?.Invoke();
            }
        }

        /// シエルに触れたことを会話サーバーへ知らせる（CielTouch から。サーバーの touch.py が声の反応を返す）
        /// strength（gentle・hard）と expression（そのときアプリが出した表情）は、ほっぺを引っ張ったときだけ付ける
        public void SendTouch(string part, string gesture, string phase, int durationMs, string strength = "", string expression = "")
        {
            if (_room == null || Status != State.Connected) return;
            var extra = strength != "" ? $",\"strength\":\"{strength}\",\"expression\":\"{expression}\"" : "";
            var json = $"{{\"v\":1,\"type\":\"user.touch\",\"part\":\"{part}\",\"gesture\":\"{gesture}\",\"phase\":\"{phase}\",\"duration_ms\":{durationMs}{extra}}}";
            try { _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes(json), reliable: true, topic: "ciel.touch"); }
            catch (Exception e) { Debug.LogWarning($"[CielConversation] タッチを送れない: {e.Message}"); }
        }

        void OnTrackUnsubscribed(IRemoteTrack track, RemoteTrackPublication publication, RemoteParticipant participant)
        {
            if (!(track is RemoteAudioTrack)) return;
            if (publication.Name == AizuchiTrack) DisposeAizuchi();
            else DisposeVoice();
        }

        void DisposeVoice()
        {
            _voiceStream?.Dispose();
            _voiceStream = null;
            if (_meter != null) Destroy(_meter.gameObject);
            _meter = null;
        }

        void DisposeAizuchi()
        {
            _aizuchiStream?.Dispose();
            _aizuchiStream = null;
            if (_aizuchiMeter != null) Destroy(_aizuchiMeter.gameObject);
            _aizuchiMeter = null;
        }

        float _mouthValue;

        void Update()
        {
            if (_volumeDirty && Time.realtimeSinceStartup - _volumeSentAt > 0.15f) SendVolume();
            if (_mouth == null) return;
            // 会話サーバーが声を小さくしても、口の開きは変えない
            var target = Mathf.Clamp01(VoiceLevel * _mouthGain);
            var t = target > _mouthValue ? _openTime : _closeTime;
            _mouthValue = Mathf.MoveTowards(_mouthValue, target, Time.deltaTime / Mathf.Max(t, 1e-3f));
            _mouth.MouthOpening = _mouthValue;
        }

        public void EndConversation()
        {
            SetMinutesRecording(false);
            DisposeVoice();
            DisposeAizuchi();
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
                _room.DataReceived -= OnDataReceived;
                _room.ParticipantConnected -= OnParticipantConnected;
                _room.ParticipantAttributesChanged -= OnParticipantAttributesChanged;
                _room.Disconnected -= OnRoomDisconnected;
                _room.ActiveSpeakersChanged -= OnActiveSpeakersChanged;
                _room.Disconnect();
                _room = null;
            }
            if (_mouth != null) _mouth.MouthOpening = 0f;
            _researchResults.Clear();
            ResearchRevision++;
            Summary = null;
            SummaryRevision++;
            _summarySeq = -1;
            _summaryParts = null;
            _speakers.Clear();
            SpeakingId = CorrectableId = "";
            SpeakingAt = -1f;
            _heard = -1;
            SpeakersRevision++;
            _serverTalk = null;
            _serverPresence = null;
            PresenceReason = "";
            AgentState = "";
            _thinkingSince = -1f;
            SetStatus(State.Disconnected);
        }

        void OnApplicationQuit()
        {
            _quitting = true;
            RestoreMinutesSleep();
        }

        void OnDestroy()
        {
            RestoreMinutesSleep();
            // 終了時は SDK の部品が先に壊れていることがあるので、片付けは OS に任せる（サンプルと同じ）
            if (!_quitting) EndConversation();
        }
    }
}
