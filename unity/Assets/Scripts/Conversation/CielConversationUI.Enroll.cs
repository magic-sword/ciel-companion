// 会話の画面（CielConversationUI）のうち、声の登録（参加者パネルの「声を登録する」から開く）。
// 本人が名前を入れて同意のボタンを押すと、会話サーバー（speakers.py）が登録を始める。画面に出す文を 1 つずつ読んでもらい、
// 会話サーバーが受け付けた数（enroll.state の accepted）で次の文に進む。読み終えたら名前と声を保存する。
// 登録の途中は、シエルは返事をしない（読み上げに答えないように）。パネルを閉じると登録をやめる。
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        // 読んでもらう文。登録のことだけを言う文にして、読んだ中身がその人のメモにならないようにする（会話サーバーもメモにしない）
        static readonly string[] EnrollSentences =
        {
            "シエル、これから私の声を覚えてもらいます。",
            "いつもと同じくらいの声で、ゆっくり読んでいます。",
            "この文は、声を聞き分けてもらうための練習です。",
            "次からは、声で私だと分かってくれるとうれしいです。",
        };

        bool _enrollOpen;          // 登録の画面を出している
        bool _enrollStarted;       // 同意して始めた（会話サーバーの知らせを待つ・受けている）
        string _enrollTarget, _enrollName;
        bool _enrollRemembered;
        int _enrollRevision = -1, _enrollStartRevision = -1;

        // 登録の画面を開く（同意の画面から）。target は札の人（無ければ null）
        void ShowEnroll(string target, string name, bool remembered)
        {
            ShowPerson(null);
            _peoplePanel.SetActive(true);
            _researchPanel.SetActive(false);
            _summaryPanel.SetActive(false);
            _enrollOpen = true;
            _enrollStarted = false;
            _enrollTarget = target;
            _enrollName = name;
            _enrollRemembered = remembered;
            _enrollRevision = _conversation.EnrollRevision;
            BuildEnrollConsent();
        }

        // パネルを閉じる・ほかの人を開くとき。登録の途中ならやめる
        void CloseEnroll()
        {
            if (!_enrollOpen) return;
            _enrollOpen = false;
            var e = _conversation != null ? _conversation.Enroll : null;
            if (_enrollStarted && e != null && e.active) _conversation.CancelEnroll();
            _enrollStarted = false;
        }

        void RefreshEnroll()
        {
            if (!_enrollOpen || !_enrollStarted || _enrollRevision == _conversation.EnrollRevision) return;
            _enrollRevision = _conversation.EnrollRevision;
            BuildEnrollReading();
        }

        void ClearEnroll(string title)
        {
            foreach (Transform child in _peopleContent) { child.gameObject.SetActive(false); Destroy(child.gameObject); }
            _peopleTitle.text = title;
        }

        // 同意の画面：何を覚えるか・いつでも消せることを見せ、名前を入れて同意のボタンを押してもらう
        void BuildEnrollConsent()
        {
            ClearEnroll(_enrollRemembered ? "声を登録し直す" : "声を登録する");
            Note(_peopleContent, _enrollRemembered
                ? $"{_enrollName}さんの声の見本を、この端末で足します。画面の文を {EnrollSentences.Length} つ、ふだんの声で読んでください。"
                : "シエルがあなたを声で分かるように、名前と声の特徴（録音そのものではなく、声の特徴を表す数字）を保存します。"
                  + "お話ししたことも少し覚えて、次の会話で使います。「私の声を忘れて」と言えば、いつでも消せます。");
            InputField input = null;
            if (!_enrollRemembered)
            {
                PanelLabel("名前");
                input = NameField(Row(_peopleContent, 40), _enrollName, 0);
            }
            var warning = Txt("Warning", _peopleContent, 11, Amber, TextAnchor.UpperLeft);
            warning.gameObject.SetActive(false);
            var ok = PanelButton(Row(_peopleContent, 44), "同意して始める", TextAnchor.MiddleCenter);
            ok.onClick.AddListener(() =>
            {
                var name = input != null ? input.text.Trim() : _enrollName;
                if (name.Length == 0)
                {
                    warning.text = "名前を入れてください。";
                    warning.gameObject.SetActive(true);
                    return;
                }
                _enrollName = name;
                _enrollStarted = true;
                _enrollRevision = _enrollStartRevision = _conversation.EnrollRevision;
                _conversation.StartEnroll(_enrollTarget, name);
                BuildEnrollReading();
            });
            var cancel = PanelButton(Row(_peopleContent, 40), "やめる", TextAnchor.MiddleCenter);
            cancel.onClick.AddListener(() => ShowPerson(null));
        }

        // 読み上げの画面：会話サーバーの enroll.state に合わせて、次の文・やり直し・結果を出す
        void BuildEnrollReading()
        {
            // 始めてからまだ知らせが無いときは、前の登録の結果を見せない
            var e = _conversation.EnrollRevision == _enrollStartRevision ? null : _conversation.Enroll;
            var waiting = e == null || (!e.active && string.IsNullOrEmpty(e.status));
            var accepted = e != null ? e.accepted : 0;
            var needed = e != null && e.needed > 0 ? e.needed : EnrollSentences.Length;
            var status = e != null ? e.status : "";
            ClearEnroll($"声の登録（{Mathf.Min(accepted + 1, needed)} / {needed}）");

            var finished = status == "saved" || (e != null && !e.active && !waiting && status != "listening");
            if (!finished)
            {
                var sentence = Txt("Sentence", _peopleContent, 20, TextMain, TextAnchor.MiddleLeft, true);
                sentence.supportRichText = false;
                sentence.text = EnrollSentences[accepted % EnrollSentences.Length];
                sentence.gameObject.AddComponent<LayoutElement>().minHeight = 90;
            }
            var (message, color) = EnrollMessage(waiting ? "starting" : status);
            var line = Txt("Status", _peopleContent, 13, color, TextAnchor.UpperLeft);
            line.supportRichText = false;
            line.text = message;

            var close = PanelButton(Row(_peopleContent, 40), finished ? "閉じる" : "やめる", TextAnchor.MiddleCenter);
            close.onClick.AddListener(() => ShowPerson(null));
        }

        static (string, Color) EnrollMessage(string status)
        {
            switch (status)
            {
                case "starting": return ("準備しています…", TextNote);
                case "enrolling":
                case "listening": return ("上の文を、ふだんの声で読んでください。", TextNote);
                case "short": return ("もう少しゆっくり、文の最後まで読んでください。", Amber);
                case "other_voice": return ("ほかの方の声が入ったようです。もう一度、同じ方が読んでください。", Amber);
                case "saving": return ("保存しています…", TextNote);
                case "saved": return ("登録できました。次からは声で分かるようになります。", Mint);
                case "name_taken": return ("同じ名前の方がいて、声が違うようです。別の呼び名で登録してください。", Amber);
                case "not_current_speaker": return ("声を登録し直すときは、先にご本人がシエルに話しかけてから始めてください。", Amber);
                case "storage_unavailable": return ("いまは保存できません。あとでもう一度試してください。", Amber);
                case "already_enrolling": return ("ほかの方の登録の途中です。終わってから始めてください。", Amber);
                case "timeout": return ("時間がたったので、登録をやめました。もう一度始めてください。", Amber);
                case "cancelled": return ("登録をやめました。", TextNote);
                default: return ("登録できませんでした。もう一度試してください。", Amber);
            }
        }
    }
}
