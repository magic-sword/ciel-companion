// 会話の画面（CielConversationUI）のうち、シエルが歌を聴いているときの表示（会話サーバーの singing.py）。
// 歌っている途中：ハートの形のときめきメーター（5 秒ごとに下から満ちていき、満タンでハートがはずんで光り、
//   小さなハートときらめきが飛び散って 0 に戻る）・ハートの数・吹き出しのひとこと。形の画像は scripts/ui/make_ui_sprites.py。
//   シエルは歌の邪魔をしないよう声を出さないので、ここに文字で出す。札（CielConversationUI.Tasks.cs）のすぐ上。
// 歌い終わって分析したら：結果のカード（ときめき度と内わけ・ぐっときた所・あなたらしさ・もう一歩）。ときめき度はシエルの主観の点数。
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        static readonly Color SongPink = Hex(0xFF8FC0);
        static readonly Color SongPinkDeep = Hex(0xFF5C9E);
        const float CommentSeconds = 4f;     // 吹き出しを出しておく秒数（最後の 1 秒で消えていく）
        const float FillSeconds = 0.35f;     // 満タンの演出の前に、ハートを満タンまで満たす秒数
        const float HeartSeconds = 1.0f;     // ハートがはずむ秒数
        const float FullSeconds = 0.8f;      // はじけたあと、満タンのまま光らせておく秒数（そのあと中身が引いて 0 から溜め直す）
        const float BurstSeconds = 1.1f;     // 小さなハートときらめきが飛び散る秒数
        const int BurstCount = 10;           // 飛び散る数（偶数番目は小さなハート、奇数番目はきらめき）

        GameObject _songLive, _songCard;
        RectTransform _songHeart, _songGlow, _songBubble, _songCardRows;
        RectTransform[] _songBurst;
        Image[] _songBurstImages;
        Text _songComment, _songScore, _songNotes, _songHeartCount;
        Image _songFillImage, _songGlowImage;
        float _songHeartSeen = -1f;   // メーターを 0 に戻した ♡（SongHeartAt）
        CanvasGroup _songBubbleGroup;
        float _songMeterShown;
        int _songResultShown;

        void BuildSong(RectTransform root)
        {
            // 歌っている途中：ハートの形のときめきメーター。声の様子の上の札（218）のさらに上
            var live = Rect("SongLive", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 272), new Vector2(220, 70));
            _songLive = live.gameObject;
            var label = Txt("Label", live, 11, TextSub, TextAnchor.MiddleRight);
            label.text = "ときめき";
            Place(label.rectTransform, Center, new Vector2(1, 0.5f), new Vector2(-40, 0), new Vector2(70, 20));
            _songHeartCount = Txt("Count", live, 14, SongPink, TextAnchor.MiddleLeft, true);
            Place(_songHeartCount.rectTransform, Center, new Vector2(0, 0.5f), new Vector2(40, 0), new Vector2(70, 22));
            // 満タンのときの光（ハートの後ろ）
            _songGlow = Rect("Glow", live, Center, Center, Vector2.zero, new Vector2(120, 120));
            _songGlowImage = Img(_songGlow, "glow", WithAlpha(SongPink, 0f));
            // ハート：うすい地・下から満ちる中身・縁
            _songHeart = Rect("Heart", live, Center, Center, Vector2.zero, new Vector2(60, 54));
            Img(_songHeart, "heart", WithAlpha(SongPink, 0.16f), child: true);
            _songFillImage = Img(_songHeart, "heart", SongPink, child: true);
            _songFillImage.type = Image.Type.Filled;
            _songFillImage.fillMethod = Image.FillMethod.Vertical;
            _songFillImage.fillOrigin = (int)Image.OriginVertical.Bottom;
            _songFillImage.fillAmount = 0f;
            Img(_songHeart, "heart_outline", SongPinkDeep, child: true);
            // 満タンのときに飛び散る、小さなハートときらめき
            _songBurst = new RectTransform[BurstCount];
            _songBurstImages = new Image[BurstCount];
            for (int i = 0; i < BurstCount; i++)
            {
                var size = i % 2 == 0 ? new Vector2(14, 13) : new Vector2(16, 16);
                _songBurst[i] = Rect("Burst", live, Center, Center, Vector2.zero, size);
                _songBurstImages[i] = Img(_songBurst[i], i % 2 == 0 ? "heart" : "sparkle", i % 2 == 0 ? SongPink : Color.white);
                _songBurst[i].gameObject.SetActive(false);
            }

            // 吹き出しのひとこと（メーターの上）
            _songBubble = Rect("SongBubble", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 330), new Vector2(240, 30));
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
        void UpdateSong() => UpdateSong(Time.unscaledTime);

        // t は今の時刻（Time.unscaledTime）。演出の途中の見た目を確かめるときに、時刻を渡して呼べる
        void UpdateSong(float t)
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
            // 満タンが届いたら：ハートを満タンまで満たし、はずませて光らせ、小さなハートときらめきを飛び散らせてから、0 に戻して溜め直す
            var since = c.SongHeartAt >= 0 ? t - c.SongHeartAt : 99f;
            if (since < FillSeconds)
                _songMeterShown = Mathf.MoveTowards(_songMeterShown, 1f, Time.unscaledDeltaTime * 4f);
            else if (since < FillSeconds + FullSeconds)
                _songMeterShown = 1f;   // はじけているあいだは満タンのまま
            else
            {
                if (c.SongHeartAt >= 0 && _songHeartSeen != c.SongHeartAt)
                    _songHeartSeen = c.SongHeartAt;   // ここから、中身が引いて溜め直す
                var rate = _songMeterShown > c.SongMeter + 0.05f ? 1.5f : 0.6f;
                _songMeterShown = Mathf.MoveTowards(_songMeterShown, c.SongMeter, Time.unscaledDeltaTime * rate);
            }
            _songFillImage.fillAmount = _songMeterShown;
            var pop = since - FillSeconds;
            // はずむ：大きくなってから、少し縮んで戻る。満タン近く（8 割より上）は、どきどきと小さく脈打つ
            var bounce = pop >= 0 && pop < HeartSeconds
                ? 1f + 0.45f * Mathf.Sin(pop / HeartSeconds * Mathf.PI * 2f) * (1f - pop / HeartSeconds)
                : _songMeterShown > 0.8f ? 1f + 0.05f * Mathf.Max(0f, Mathf.Sin(t * Mathf.PI * 2.4f)) : 1f;
            _songHeart.localScale = new Vector3(bounce, bounce, 1);
            _songFillImage.color = Color.Lerp(SongPink, Color.white, since < FillSeconds + 0.25f ? 0.55f : 0f);
            // 光：ぱっと広がって消える
            var glow = pop >= 0 && pop < 0.8f ? 1f - pop / 0.8f : 0f;
            _songGlowImage.color = WithAlpha(SongPink, 0.85f * glow);
            var glowScale = 0.7f + 0.9f * (1f - glow);
            _songGlow.localScale = new Vector3(glowScale, glowScale, 1);
            // 小さなハートときらめき：まわりへ飛び散り、少し浮いて消える
            for (int i = 0; i < BurstCount; i++)
            {
                var on = pop >= 0 && pop < BurstSeconds;
                if (_songBurst[i].gameObject.activeSelf != on) _songBurst[i].gameObject.SetActive(on);
                if (!on) continue;
                var p = pop / BurstSeconds;
                var ease = 1f - (1f - p) * (1f - p);
                var angle = (i * 360f / BurstCount + 18f) * Mathf.Deg2Rad;
                var dist = 30f + (i % 2 == 0 ? 62f : 48f) * ease;
                _songBurst[i].anchoredPosition = new Vector2(Mathf.Cos(angle) * dist, Mathf.Sin(angle) * dist * 0.8f + 14f * ease);
                var scale = (i % 2 == 0 ? 1.2f : 1f) * (1f - 0.5f * p);
                _songBurst[i].localScale = new Vector3(scale, scale, 1);
                _songBurst[i].localRotation = Quaternion.Euler(0, 0, i % 2 == 0 ? 0f : 180f * p);
                var color = _songBurstImages[i].color;
                _songBurstImages[i].color = new Color(color.r, color.g, color.b, 1f - p * p);
            }
            var count = c.SongHearts > 0 ? $"×{c.SongHearts}" : "";
            if (_songHeartCount.text != count) _songHeartCount.text = count;
            var age = c.SongCommentAt >= 0 ? t - c.SongCommentAt : 99f;
            var show = age < CommentSeconds && c.SongComment != "";
            if (_songBubble.gameObject.activeSelf != show) _songBubble.gameObject.SetActive(show);
            if (show)
            {
                if (_songComment.text != c.SongComment) _songComment.text = c.SongComment;
                _songBubbleGroup.alpha = Mathf.Clamp01(CommentSeconds - age);
                var rise = Mathf.Clamp01(age / 0.3f);
                _songBubble.anchoredPosition = new Vector2(0, 322 + 8 * rise);
            }
        }
    }
}
