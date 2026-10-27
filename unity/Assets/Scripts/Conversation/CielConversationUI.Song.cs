// 会話の画面（CielConversationUI）のうち、シエルが歌を聴いているときの表示（会話サーバーの singing.py）。
// 歌っている途中：ときめきメーター（5 秒ごとの心に響いた度）・♡（ぐっときた・盛り上がり・展開の変化）・吹き出しのひとこと。
//   シエルは歌の邪魔をしないよう声を出さないので、ここに文字で出す。札（CielConversationUI.Tasks.cs）のすぐ上。
// 歌い終わって分析したら：結果のカード（ときめき度と内わけ・ぐっときた所・あなたらしさ・もう一歩）。ときめき度はシエルの主観の点数。
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        static readonly Color SongPink = Hex(0xFF8FC0);
        const float MeterWidth = 168f;
        const float CommentSeconds = 4f;     // 吹き出しを出しておく秒数（最後の 1 秒で消えていく）
        const float HeartSeconds = 1.2f;     // ♡ がはずむ秒数

        GameObject _songLive, _songCard;
        RectTransform _songFill, _songHeart, _songBubble, _songCardRows;
        Text _songComment, _songScore, _songNotes;
        CanvasGroup _songBubbleGroup;
        float _songMeterShown;
        int _songResultShown;

        void BuildSong(RectTransform root)
        {
            // 歌っている途中：ときめきメーターと ♡。声の様子の上の札（218）のさらに上
            var live = Rect("SongLive", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 252), new Vector2(286, 30));
            Pill(live, new Color(0.04f, 0.13f, 0.20f, 0.6f));
            Edge(live, WithAlpha(SongPink, 0.5f));
            _songLive = live.gameObject;
            var label = Txt("Label", live, 11, TextSub, TextAnchor.MiddleLeft);
            label.text = "ときめき";
            Place(label.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(14, 0), new Vector2(60, 20));
            var track = Rect("Track", live, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(72, 0), new Vector2(MeterWidth, 8));
            Pill(track, WithAlpha(TextNote, 0.25f));
            _songFill = Rect("Fill", track, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(0, 8));
            Pill(_songFill, SongPink);
            var heart = Txt("Heart", live, 18, SongPink, TextAnchor.MiddleCenter, true);
            heart.text = "♥";
            _songHeart = heart.rectTransform;
            Place(_songHeart, new Vector2(1, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-22, 1), new Vector2(28, 28));

            // 吹き出しのひとこと（メーターの上）
            _songBubble = Rect("SongBubble", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 288), new Vector2(240, 30));
            Pill(_songBubble, new Color(0.20f, 0.06f, 0.14f, 0.78f));
            Edge(_songBubble, WithAlpha(SongPink, 0.75f));
            _songBubbleGroup = _songBubble.gameObject.AddComponent<CanvasGroup>();
            _songComment = Txt("Comment", _songBubble, 13, TextMain, TextAnchor.MiddleCenter, true);
            _songComment.supportRichText = false;
            Stretch(_songComment.rectTransform);
            _songBubble.gameObject.SetActive(false);
            _songLive.SetActive(false);

            // 歌い終わったときの結果のカード
            var card = Rect("SongCard", root, Center, Center, new Vector2(0, 40), new Vector2(330, 392));
            Rounded(card, SheetColor, 18, raycast: true);
            _songCard = card.gameObject;
            var close = Rect("Close", card, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var closeButton = close.gameObject.AddComponent<Button>();
            closeButton.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            closeButton.onClick.AddListener(() => _songCard.SetActive(false));
            var title = Txt("Title", card, 15, TextMain, TextAnchor.MiddleLeft, true);
            title.text = "シエルのときめき度";
            Place(title.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -18), new Vector2(240, 26));
            _songScore = Txt("Score", card, 46, SongPink, TextAnchor.MiddleCenter, true);
            Place(_songScore.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -50), new Vector2(240, 60));
            var note = Txt("Note", card, 10, TextNote, TextAnchor.MiddleCenter);
            note.text = "正しさではなく、シエルがどれだけときめいたか";
            Place(note.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -110), new Vector2(300, 16));
            _songCardRows = Rect("Rows", card, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -134), new Vector2(290, 112));
            _songNotes = Txt("Notes", card, 12, TextSub, TextAnchor.UpperLeft);
            _songNotes.supportRichText = false;
            Place(_songNotes.rectTransform, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -258), new Vector2(290, 120));
            _songCard.SetActive(false);
        }

        // 結果が届いたら、カードを作り直して開く
        void RefreshSong()
        {
            if (_songCard == null || _conversation == null) return;
            var r = _conversation.SongResult;
            if (r == null || _conversation.SongResultRevision == _songResultShown) return;
            _songResultShown = _conversation.SongResultRevision;
            _songScore.text = $"{r.score}<size=20> 点</size>";
            for (int i = _songCardRows.childCount - 1; i >= 0; i--) Destroy(_songCardRows.GetChild(i).gameObject);
            var parts = r.parts ?? new CielConversation.SongPart[0];
            for (int i = 0; i < parts.Length; i++)
            {
                var p = parts[i];
                var row = Rect("Row", _songCardRows, new Vector2(0, 1), new Vector2(0, 1), new Vector2(0, -i * 28), new Vector2(290, 24));
                var name = Txt("Name", row, 12, TextSub, TextAnchor.MiddleLeft);
                name.text = p.name;
                Place(name.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero, new Vector2(100, 20));
                var track = Rect("Track", row, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(104, 0), new Vector2(136, 7));
                Pill(track, WithAlpha(TextNote, 0.25f));
                var fill = Rect("Fill", track, new Vector2(0, 0.5f), new Vector2(0, 0.5f), Vector2.zero,
                    new Vector2(136 * (p.max > 0 ? Mathf.Clamp01((float)p.value / p.max) : 0), 7));
                Pill(fill, SongPink);
                var value = Txt("Value", row, 11, TextNote, TextAnchor.MiddleRight);
                value.text = $"{p.value}/{p.max}";
                Place(value.rectTransform, new Vector2(1, 0.5f), new Vector2(1, 0.5f), Vector2.zero, new Vector2(44, 20));
            }
            var lines = new System.Text.StringBuilder();
            var moments = r.moments ?? new CielConversation.SongMoment[0];
            if (moments.Length > 0)
            {
                lines.Append("ぐっときた所");
                foreach (var m in moments) lines.Append($"\n・{Clock(m.start)}〜{Clock(m.end)}（{m.why}）");
            }
            if (!string.IsNullOrEmpty(r.habits)) lines.Append($"{(lines.Length > 0 ? "\n" : "")}あなたらしさ：{r.habits}");
            if (r.hint_at >= 0)
                lines.Append($"{(lines.Length > 0 ? "\n" : "")}もう一歩：{Clock(r.hint_at)}{(r.hint_kind == "wobble" ? " の伸ばす音" : " の音")}");
            _songNotes.text = lines.ToString();
            _songCard.SetActive(true);
        }

        static string Clock(float seconds)
        {
            var s = Mathf.Max(0, Mathf.RoundToInt(seconds));
            return $"{s / 60}:{s % 60:00}";
        }

        // 歌っている途中の表示（Update から毎フレーム）。メーターはなめらかに追い、♡ ははずみ、吹き出しは消えていく
        void UpdateSong()
        {
            if (_songLive == null) return;
            var c = _conversation;
            var listening = c.Status == CielConversation.State.Connected && c.SongState == "listening";
            if (_songLive.activeSelf != listening) _songLive.SetActive(listening);
            if (!listening)
            {
                _songMeterShown = 0f;
                if (_songBubble.gameObject.activeSelf) _songBubble.gameObject.SetActive(false);
                return;
            }
            var t = Time.unscaledTime;
            _songMeterShown = Mathf.MoveTowards(_songMeterShown, c.SongMeter, Time.unscaledDeltaTime * 0.6f);
            _songFill.sizeDelta = new Vector2(MeterWidth * _songMeterShown, 8);
            var since = c.SongHeartAt >= 0 ? t - c.SongHeartAt : 99f;
            var bounce = since < HeartSeconds ? 1f + 0.45f * Mathf.Sin(since / HeartSeconds * Mathf.PI) : 1f;
            _songHeart.localScale = new Vector3(bounce, bounce, 1);
            var age = c.SongCommentAt >= 0 ? t - c.SongCommentAt : 99f;
            var show = age < CommentSeconds && c.SongComment != "";
            if (_songBubble.gameObject.activeSelf != show) _songBubble.gameObject.SetActive(show);
            if (show)
            {
                if (_songComment.text != c.SongComment) _songComment.text = c.SongComment;
                _songBubbleGroup.alpha = Mathf.Clamp01(CommentSeconds - age);
                var rise = Mathf.Clamp01(age / 0.3f);
                _songBubble.anchoredPosition = new Vector2(0, 280 + 8 * rise);
            }
        }
    }
}
