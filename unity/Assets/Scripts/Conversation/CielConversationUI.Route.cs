// 会話の画面（CielConversationUI）のうち、設定の「声のつなぎ方」（PC だけ。そのほかのタブ）。
// ふだん｜会議 を選ぶと、マイクと声の出力の組がまとめて変わる（CielConversation.Route.cs）。選べるのは、いまのつなぎ方の組。
// 会議では、選ぶ欄の名前を役目（会議の音を聞く・会議へ話す）で書き、「自動」は見つけた仮想オーディオケーブルを使う。
// 会議の確かめ：会議の音が届いているか（マイクを入れていると、だれかが話すたびに光る）と、シエルの声を試しに流すボタン。
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        static readonly string[] RouteLabels = { "ふだん", "会議" };
        const float HeardHoldSeconds = 2f;   // 会議の音が届いたら、この秒数は「届いています」と見せる

        readonly List<(Image fill, Image edge, Text label)> _routeSegs = new List<(Image, Image, Text)>();
        Text _routeNote, _heardText, _voiceTestText;
        GameObject _meetingCheck;

        // PC だけ：声のつなぎ方と、その組のマイクとスピーカー。会議では、届いているかの確かめ
        void BuildDevicesSection(RectTransform content)
        {
            var sec = Section(content);
            _devicesSection = sec.gameObject;
            SectionLabel(Row(sec, 20), "声のつなぎ方");
            Segmented(sec, RouteLabels, i => _conversation.SelectRoute((CielConversation.Route)i), _routeSegs);
            _routeNote = Txt("Note", sec, 12, TextSub, TextAnchor.UpperLeft);
            _devices = NewDropdown(Row(sec, 44), "MicDevice");
            _devices.onValueChanged.AddListener(i => _conversation.SelectMic(i <= 0 ? null : _deviceGuids[i]));
            _speakers = NewDropdown(Row(sec, 44), "SpeakerDevice");
            _speakers.onValueChanged.AddListener(i => _conversation.SelectSpeaker(i <= 0 ? null : _speakerGuids[i]));

            var check = Section(sec);
            _meetingCheck = check.gameObject;
            _heardText = Txt("Heard", check, 13, TextMain, TextAnchor.UpperLeft, true);
            var test = PanelButton(Row(check, 40), "シエルの声を試しに流す", TextAnchor.MiddleCenter);
            test.onClick.AddListener(() => _conversation.TestVoice());
            _voiceTestText = Txt("VoiceTest", check, 12, TextSub, TextAnchor.UpperLeft);
            Note(check, "会議のブラウザでは、シエル用の参加者のマイクを「CABLE Output」、スピーカーを「Hi-Fi Cable Input」にします"
                + "（ブラウザがサイトごとに覚えるので、初回だけ）");
        }

        // 設定画面の表示を合わせる（RefreshSettings から）
        void RefreshRoute()
        {
            var c = _conversation;
            _devicesSection.SetActive(c.CanSelectRoute && (c.CanSelectMic || c.CanSelectSpeaker));
            var meeting = c.InMeeting;
            ShowSelected(_routeSegs, (int)c.RouteChoice);
            var missing = c.RouteMissing;
            _routeNote.text = !meeting
                ? "自分のマイクとスピーカーで話します。"
                : "会議のブラウザと仮想オーディオケーブルでつなぎます。マイクは入れたままにします。"
                  + (missing == "both" ? "\n仮想オーディオケーブルが見つかりません。VB-Audio の Virtual Cable と Hi-Fi Cable を入れるか、下で選んでください。"
                    : missing == "listen" ? "\n会議の音を聞く仮想ケーブル（Hi-Fi Cable Output など）が見つかりません。下で選んでください。"
                    : missing == "speak" ? "\n会議へ話す仮想ケーブル（CABLE Input など）が見つかりません。下で選んでください。" : "");
            _routeNote.color = missing != "" ? Amber : TextSub;
            RefreshDevices(_devices, _deviceGuids, c.CanSelectMic, c.MicDevices, c.SelectedMic,
                meeting ? AutoLabel(c.MicDevices, c.AutoMeetingMic) : "既定のマイク（OS の設定）", meeting ? "会議の音を聞く：" : "マイク：");
            RefreshDevices(_speakers, _speakerGuids, c.CanSelectSpeaker, c.SpeakerDevices, c.SelectedSpeaker,
                meeting ? AutoLabel(c.SpeakerDevices, c.AutoMeetingSpeaker) : "既定のスピーカー（OS の設定）", meeting ? "会議へ話す：" : "声の出力：");
            _meetingCheck.SetActive(meeting);
            UpdateMeetingCheck();
        }

        // 欄に収まるよう、機器の名前の後ろのドライバー名（「 (VB-Audio Hi-Fi Cable)」など）は外す
        static string AutoLabel(List<(string name, string guid)> devices, string guid)
        {
            if (guid == null) return "自動（見つかりません）";
            var name = devices.Find(d => d.guid == guid).name ?? "";
            var cut = name.IndexOf(" (", System.StringComparison.Ordinal);
            return "自動 ― " + (cut > 0 ? name.Substring(0, cut) : name);
        }

        // 会議の確かめの文（時間で変わるので、設定画面を開いているあいだは毎フレーム。UpdateSheet から）
        void UpdateMeetingCheck()
        {
            if (_meetingCheck == null || !_meetingCheck.activeInHierarchy) return;
            var c = _conversation;
            var now = Time.unscaledTime;
            string heard;
            Color color;
            if (c.Status != CielConversation.State.Connected) (heard, color) = ("会議の音：つないでいません", TextSub);
            else if (!c.MicEnabled) (heard, color) = ("会議の音：マイクが切れています（入れると、届いているか分かります）", Amber);
            else if (c.UserSpeaking || (c.UserHeardAt >= 0 && now - c.UserHeardAt < HeardHoldSeconds))
                (heard, color) = ("● 会議の音が届いています", Mint);
            else if (c.UserHeardAt >= 0) (heard, color) = ($"会議の音：最後に届いたのは {Mathf.FloorToInt(now - c.UserHeardAt)} 秒前", TextSub);
            else (heard, color) = ("会議の音：まだ届いていません。会議でだれかが話すと、ここが光ります", TextSub);
            if (_heardText.text != heard) _heardText.text = heard;
            _heardText.color = color;

            var since = now - c.VoiceTestAt;
            var test = c.VoiceTestState switch
            {
                "sending" when since > 5f => "会話サーバーから返事がありません。つながっているか確かめてください",
                "sending" => "頼んでいます…",
                "playing" when since < 6f || c.VoiceLevel > 0.02f => "シエルの声を流しています。会議で聞こえれば、つながっています",
                "playing" => "流しました。会議で聞こえなければ、会議のブラウザのマイクが「CABLE Output」か確かめてください",
                "failed" when c.VoiceTestReason == "not_ready" => "まだ流せません（シエルが準備中）。少し待ってから、もう一度押してください",
                "failed" when c.VoiceTestReason == "tts" => "流せません（読み上げのサーバーが動いていない）",
                "failed" => "流せません（会話サーバーへ送れない）",
                _ => "",
            };
            if (_voiceTestText.text != test) _voiceTestText.text = test;
            _voiceTestText.color = c.VoiceTestState == "failed" ? Amber : TextSub;
        }
    }
}
