// 会話（CielConversation）のうち、心の考え（会話サーバーの mind_view.py が送る mind.ideas）。
// シエルが相手の発言ごとに考えた話したいこと・点・理由と、話したか落としたかを持つ。読むのは CielProcessWindow.cs。
// 記録なので鮮度は数えない。会話が切れたら消す。
using System;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        [Serializable]
        public class MindIdea
        {
            public string kind, text, pro, con;
            public int score;
            public float weighted, level;   // weighted：書き出し確率で重みを付けた点。取れないときは -1
        }

        [Serializable]
        public class MindCard
        {
            public int id, turn, chosen;
            public string heard, phase, reason;   // phase：waiting_reply・thinking・thought・none・scheduled・spoken・dropped・aborted
            public float ms, ago;
            public MindIdea[] ideas;
        }

        [Serializable]
        public class MindIdeasState
        {
            public string type, stream_id, presence;
            public int v, revision;
            public bool speak;
            public float threshold;   // 自分から話す基準。無いときは -1
            public MindCard[] cards;
        }

        /// 心の考え（届いていなければ null）
        public MindIdeasState Mind { get; private set; }
        public float MindAt { get; private set; }
        string _mindStream;
        int _mindRevision;

        void OnMindIdeas(byte[] data)
        {
            MindIdeasState s;
            try { s = JsonUtility.FromJson<MindIdeasState>(System.Text.Encoding.UTF8.GetString(data)); }
            catch (Exception) { return; }
            if (s == null || s.type != "mind.ideas" || s.v != 1 || string.IsNullOrEmpty(s.stream_id) || s.revision < 1) return;
            if (_mindStream == s.stream_id && s.revision <= _mindRevision) return;
            _mindStream = s.stream_id;
            _mindRevision = s.revision;
            s.cards ??= Array.Empty<MindCard>();
            Mind = s;
            MindAt = Time.unscaledTime;
            Changed?.Invoke();
        }

        void ResetMind()
        {
            Mind = null;
            _mindStream = null;
            _mindRevision = 0;
        }
    }

    // 心の考えの見せ方（言葉と色）。操作画面・配信映像で同じ言葉を使う。
    public static class CielMindPresentation
    {
        public static string Kind(string kind) => kind switch
        {
            "ask" => "聞きたい", "correct" => "訂正", "recall" => "思い出した", "suggest" => "提案", "feel" => "気持ち", _ => kind ?? ""
        };

        public static string Phase(CielConversation.MindCard c) => c.phase switch
        {
            "waiting_reply" => "返事を読むのを待っています",
            "thinking" => "考えています",
            "thought" => "考えました",
            "none" => "話したいことはありません",
            "scheduled" => "話す言葉を作っています",
            "spoken" => "話しました",
            "aborted" => "相手が話し始めたので止めました",
            "dropped" => "話しません：" + Reason(c.reason),
            _ => c.phase ?? ""
        };

        public static string Reason(string reason) => reason switch
        {
            "low" => "基準より低い",
            "mode" => "ひとりで、ふつう・おしゃべりのときだけ話す",
            "no_reply" => "返事がまだ無い",
            "user_speaking" => "相手が話している",
            "repeat" => "返事と同じことになる",
            "user_spoke" => "相手が話し始めた",
            _ => reason ?? ""
        };

        // 状態の色：考え中はシアン、話す予定はアンバー、話したは緑、落とした・止めたはグレー（配信画面の決まり）
        public static Color Tone(string phase) => phase switch
        {
            "waiting_reply" or "thinking" => new Color(.5f, .91f, 1),
            "scheduled" => new Color(1, .77f, .42f),
            "spoken" => new Color(.36f, .94f, .55f),
            "thought" => new Color(.94f, .98f, 1),
            _ => new Color(.56f, .66f, .71f)
        };

        /// ひとり（solo）以外では、考えの文を隠す（記憶から誰かの話が入ることがある）
        public static bool ShowText(CielConversation.MindIdeasState s) => s != null && s.presence == "solo" && !HideText;
        /// 配信者が、ひとりのときも文を隠す（設定）
        public static bool HideText
        {
            get => PlayerPrefs.GetInt("ciel.mind.hideText", 0) == 1;
            set { PlayerPrefs.SetInt("ciel.mind.hideText", value ? 1 : 0); PlayerPrefs.Save(); }
        }
    }
}
