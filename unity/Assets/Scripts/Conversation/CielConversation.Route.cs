// 会話（CielConversation）のうち、声のつなぎ方と、会議の確かめと、会話サーバーの不調の知らせ。
// つなぎ方（PC だけ）：ふだん（自分のマイクとスピーカー）・会議（仮想オーディオケーブルで、会議のブラウザとつなぐ）。
// それぞれがマイクと声の出力の組を覚え（PlayerPrefs）、切り替えると両方が変わる。会議かどうかもこれで決め、会話サーバーへ送る
// （以前は、声の出力の名前に CABLE が入っているかで推し量っていた）。
// 会議の組で選んでいない向きは、仮想オーディオケーブルを名前の頭で探して使う（会議の音を聞く：Hi-Fi Cable Output など、
// 会議へ話す：CABLE Input など）。見つからなければ OS の既定のまま、画面で知らせる（RouteMissing）。
// 以前の版で保存した機器が仮想ケーブルなら、会議の組へ移し、ふだんの組は OS の既定にする（2026-11-02。会議の配線のまま
// 起動して、話しかけても届かず、シエルの声も聞こえなかった）。
// 会議の確かめ：会議の音が届いたか（UserHeardAt。LiveKit の「話している人」に自分が入った時刻）と、シエルの声を試しに流す
// （TestVoice。会話サーバー server/agent/soundcheck.py が、会話モデルを使わずに決まった一言を流す）。
// 会話サーバーの不調（agent.problem。server/agent/health.py）：残高切れなどで聞き取り・返事ができない・会話が止まった。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        public enum Route { Everyday, Meeting }

        const string RoutePrefKey = "ciel.route";
        const string MeetingMicPrefKey = "ciel.meeting.micDevice";
        const string MeetingSpeakerPrefKey = "ciel.meeting.speakerDevice";
        const float ProblemShowSeconds = 60f;   // 会話が止まっていない不調は、この秒数で表示を消す

        [Tooltip("会議の音を聞くマイク（仮想オーディオケーブルの出口）として探す、機器の名前の頭。前にあるものから使う")]
        [SerializeField] string[] _meetingListenNames = { "Hi-Fi Cable Output", "CABLE-B Output", "VoiceMeeter Out" };
        [Tooltip("会議へ話す声の出力（仮想オーディオケーブルの入口）として探す、機器の名前の頭。前にあるものから使う")]
        [SerializeField] string[] _meetingSpeakNames = { "CABLE Input", "CABLE-A Input", "VoiceMeeter Input" };

        public Route RouteChoice { get; private set; } = Route.Everyday;
        /// PC だけ（スマホは OS が機器を切り替える）
        public bool CanSelectRoute => !Application.isMobilePlatform;
        public bool InMeeting => CanSelectRoute && RouteChoice == Route.Meeting;
        /// 会議の組で、仮想オーディオケーブルが見つからなかった向き（"listen"：会議の音を聞く、"speak"：会議へ話す、両方なら "both"）
        public string RouteMissing { get; private set; } = "";
        /// 会議の組で、選んでいない向きに使う機器（名前から探したもの。無ければ null）
        public string AutoMeetingMic { get; private set; }
        public string AutoMeetingSpeaker { get; private set; }

        /// 自分の声（会議では、会議の音）が最後に会話サーバーへ届いた時刻（Time.unscaledTime。まだなら -1）
        public float UserHeardAt { get; private set; } = -1f;

        /// シエルの声を試しに流した結果：""（まだ）・sending（頼んだ）・playing（流し始めた）・failed（流せない。VoiceTestReason）
        public string VoiceTestState { get; private set; } = "";
        public string VoiceTestReason { get; private set; } = "";
        public float VoiceTestAt { get; private set; } = -1f;

        /// 会話サーバーの不調（""・quota・auth・rate_limit・error）と、失敗した係（stt・llm・tts・other）、会話が止まったか
        public string Problem => ProblemStopped || (ProblemAt >= 0 && Time.unscaledTime - ProblemAt < ProblemShowSeconds) ? _problem : "";
        public string ProblemService { get; private set; } = "";
        public bool ProblemStopped { get; private set; }
        public float ProblemAt { get; private set; } = -1f;
        string _problem = "";

        string MicKey => RouteChoice == Route.Meeting ? MeetingMicPrefKey : MicPrefKey;
        string SpeakerKey => RouteChoice == Route.Meeting ? MeetingSpeakerPrefKey : SpeakerPrefKey;
        // 実際に使う機器（null は OS の既定）
        string MicChoice => _micGuid ?? (InMeeting ? AutoMeetingMic : null);
        string SpeakerChoice => _speakerGuid ?? (InMeeting ? AutoMeetingSpeaker : null);

        // Start で読む（機器の一覧は、つないだときに分かる。ResolveRouteDevices）
        void LoadRoute()
        {
            RouteChoice = (Route)Mathf.Clamp(PlayerPrefs.GetInt(RoutePrefKey, 0), 0, 1);
            LoadRouteDevices();
        }

        void LoadRouteDevices()
        {
            _micGuid = PlayerPrefs.HasKey(MicKey) ? PlayerPrefs.GetString(MicKey) : null;
            _speakerGuid = PlayerPrefs.HasKey(SpeakerKey) ? PlayerPrefs.GetString(SpeakerKey) : null;
        }

        // 機器の一覧が分かったあと（Connect）。以前の設定を移し、今は無い機器を外し、会議の組の仮想ケーブルを探す
        void ResolveRouteDevices()
        {
            if (!PlayerPrefs.HasKey(RoutePrefKey) && CanSelectRoute) MigrateToRoutes();
            if (_micGuid != null && !MicDevices.Exists(m => m.guid == _micGuid)) _micGuid = null;
            if (_speakerGuid != null && !SpeakerDevices.Exists(m => m.guid == _speakerGuid)) _speakerGuid = null;
            AutoMeetingMic = FindByPrefix(MicDevices, _meetingListenNames);
            AutoMeetingSpeaker = FindByPrefix(SpeakerDevices, _meetingSpeakNames);
            UpdateRouteMissing();
            Debug.Log($"[CielConversation] つなぎ方：{(InMeeting ? "会議" : "ふだん")}（会議の音を聞く：{Name(MicDevices, AutoMeetingMic)}、"
                      + $"会議へ話す：{Name(SpeakerDevices, AutoMeetingSpeaker)}）");
        }

        // 以前の版は組が 1 つだった。保存していた機器が仮想ケーブルなら会議の組へ移し、ふだんは OS の既定から始める
        void MigrateToRoutes()
        {
            var mic = Name(MicDevices, _micGuid);
            var speaker = Name(SpeakerDevices, _speakerGuid);
            var meetingMic = _micGuid != null && StartsWithAny(mic, _meetingListenNames);
            var meetingSpeaker = _speakerGuid != null && StartsWithAny(speaker, _meetingSpeakNames);
            if (meetingMic || meetingSpeaker)
            {
                if (meetingMic) { PlayerPrefs.SetString(MeetingMicPrefKey, _micGuid); PlayerPrefs.DeleteKey(MicPrefKey); }
                if (meetingSpeaker) { PlayerPrefs.SetString(MeetingSpeakerPrefKey, _speakerGuid); PlayerPrefs.DeleteKey(SpeakerPrefKey); }
                Debug.Log($"[CielConversation] 以前の設定の仮想ケーブル（マイク {(meetingMic ? mic : "-")}、声の出力 {(meetingSpeaker ? speaker : "-")}）を、会議のつなぎ方へ移した");
            }
            RouteChoice = Route.Everyday;
            PlayerPrefs.SetInt(RoutePrefKey, (int)Route.Everyday);
            PlayerPrefs.Save();
            LoadRouteDevices();
        }

        void UpdateRouteMissing()
        {
            var listen = MicChoice == null;
            var speak = SpeakerChoice == null;
            RouteMissing = !InMeeting ? "" : listen && speak ? "both" : listen ? "listen" : speak ? "speak" : "";
        }

        /// つなぎ方を変える。マイクと声の出力をその組に切り替え、会話サーバーへ会議かどうかを知らせる。会議にしたらマイクを入れる
        public void SelectRoute(Route route)
        {
            if (!CanSelectRoute || route == RouteChoice) return;
            RouteChoice = route;
            PlayerPrefs.SetInt(RoutePrefKey, (int)route);
            LoadRouteDevices();
            UpdateRouteMissing();
            _serverTalk = null;   // 会話サーバーの返事が来るまでは、選んだ設定で表示する
            _serverPresence = null;
            Debug.Log($"[CielConversation] つなぎ方を{(route == Route.Meeting ? "会議" : "ふだん")}にした");
            if (_platformAudio != null) ApplySpeaker();
            if (_recording || _busy) StartCoroutine(RestartMic());
            else if (route == Route.Meeting && Status == State.Connected) SetMicEnabled(true);   // 会議の音は、入れておかないと届かない
            SendStyle();
            Changed?.Invoke();
        }

        /// シエルの声を試しに流す（会議へ届くかの確かめ）。会話サーバーが決まった一言を、いまの声の出力へ流す
        public void TestVoice()
        {
            if (_room == null || Status != State.Connected) return;
            try
            {
                _room.LocalParticipant.PublishData(System.Text.Encoding.UTF8.GetBytes("{\"v\":1,\"type\":\"voice.test\"}"),
                    reliable: true, topic: "ciel.soundcheck");
                (VoiceTestState, VoiceTestReason, VoiceTestAt) = ("sending", "", Time.unscaledTime);
                Debug.Log("[CielConversation] シエルの声を試しに流すよう頼んだ");
            }
            catch (Exception e)
            {
                (VoiceTestState, VoiceTestReason, VoiceTestAt) = ("failed", "send", Time.unscaledTime);
                Debug.LogWarning($"[CielConversation] 声の確かめを頼めない: {e.Message}");
            }
            Changed?.Invoke();
        }

        /// 会話が止まったときなどに、つなぎ直す
        public void Reconnect()
        {
            if (Status == State.Connecting) return;
            EndConversation();
            StartConversation();
        }

        void OnVoiceTest(EventJson e)
        {
            (VoiceTestState, VoiceTestReason, VoiceTestAt) = (e.state ?? "", e.reason ?? "", Time.unscaledTime);
            Debug.Log($"[CielConversation] 声の確かめ：{VoiceTestState}{(VoiceTestReason != "" ? $"（{VoiceTestReason}）" : "")}");
            Changed?.Invoke();
        }

        void OnProblem(EventJson e)
        {
            _problem = string.IsNullOrEmpty(e.kind) ? "error" : e.kind;
            ProblemService = e.service ?? "";
            ProblemStopped |= e.stopped;
            ProblemAt = Time.unscaledTime;
            Debug.LogWarning($"[CielConversation] 会話サーバーの不調：{_problem}（{ProblemService}）{(e.stopped ? "。会話が止まった" : "")}");
            Changed?.Invoke();
        }

        // つなぐたびに、前の会話の不調・声の確かめを忘れる
        void ClearRouteChecks()
        {
            (_problem, ProblemService, ProblemStopped, ProblemAt) = ("", "", false, -1f);
            (VoiceTestState, VoiceTestReason, VoiceTestAt) = ("", "", -1f);
            UserHeardAt = -1f;
        }

        static string FindByPrefix(System.Collections.Generic.List<(string name, string guid)> devices, string[] prefixes)
        {
            foreach (var p in prefixes)
                foreach (var d in devices)
                    if (!string.IsNullOrEmpty(p) && (d.name ?? "").StartsWith(p, StringComparison.OrdinalIgnoreCase)) return d.guid;
            return null;
        }

        static bool StartsWithAny(string name, string[] prefixes) =>
            Array.Exists(prefixes, p => !string.IsNullOrEmpty(p) && (name ?? "").StartsWith(p, StringComparison.OrdinalIgnoreCase));

        static string Name(System.Collections.Generic.List<(string name, string guid)> devices, string guid) =>
            guid == null ? "なし" : devices.Find(m => m.guid == guid).name ?? guid;
    }
}
