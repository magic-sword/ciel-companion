// 会話の画面（CielConversationUI）のうち、「ほか（＋）」のメニュー。下のボタンにはよく使うマイクと声だけを出し、
// ときどき使うもの（画像を見せる・まとめ）はここにまとめる（スマホの幅で、ボタンが画面の外へ出ないように。2026-11-06）。
// 機能が増えたら、ここに行を足す。＋のボタンは、議事録をとっているあいだは琥珀にし、画像を送ったあとは数秒だけ様子を出す。
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        GameObject _morePop;
        Text _moreImageText, _moreSummaryText;
        Image _moreImageIcon, _moreSummaryIcon;

        void BuildMorePop(RectTransform root)
        {
            _morePop = new GameObject("MorePop", typeof(RectTransform));
            var pop = (RectTransform)_morePop.transform;
            pop.SetParent(root, false);
            Stretch(pop);
            // 外を押したら閉じる（声の大きさのつまみと同じ作り）
            var blockerRect = Rect("Blocker", pop, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(blockerRect);
            Img(blockerRect, null, Color.clear, raycast: true).gameObject.AddComponent<Button>().onClick.AddListener(() => ShowMorePop(false));

            var area = Rect("Safe", pop, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            Stretch(area);
            area.gameObject.AddComponent<SafeArea>();

            var rows = new List<(string icon, Action click, Action<Image, Text> keep)>();
            if (WindowsFileDialog.Available)
                rows.Add(("image", () => { ShowMorePop(false); _conversation.PickAndShareImage(); },
                          (i, t) => (_moreImageIcon, _moreImageText) = (i, t)));
            rows.Add(("minutes", () => { ShowMorePop(false); ShowSummary(true); },
                      (i, t) => (_moreSummaryIcon, _moreSummaryText) = (i, t)));

            const float rowH = 48, pad = 6, width = 210;
            var height = rows.Count * rowH + pad * 2;
            // ＋のボタンの真上。画面の左の端から出ないよう、左の端をそろえる
            var panel = Rect("Panel", area, new Vector2(0.5f, 0), new Vector2(0, 0), new Vector2(-132 - 32, 128), new Vector2(width, height));
            Rounded(panel, new Color(0.04f, 0.13f, 0.20f, 0.92f), 16, raycast: true);
            SetRadius(Img(panel, "circle_outline", WithAlpha(Cyan, 0.55f), child: true), 16);   // 角丸の縁（Edge はカプセル用）
            for (int n = 0; n < rows.Count; n++)
            {
                var (icon, click, keep) = rows[n];
                var row = Rect("Row", panel, new Vector2(0, 1), new Vector2(0, 1), new Vector2(pad, -pad - n * rowH), new Vector2(width - pad * 2, rowH));
                var hit = Rounded(row, Color.clear, 12, raycast: true);
                var iconImage = Icon(row, icon, 18, Hex(0xE6F8FF));
                Place(iconImage.rectTransform, new Vector2(0, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(24, 0), new Vector2(18, 18));
                var text = Txt("Text", row, 14, TextMain, TextAnchor.MiddleLeft);
                Place(text.rectTransform, new Vector2(0, 0.5f), new Vector2(0, 0.5f), new Vector2(46, 0), new Vector2(width - 60, 24));
                text.horizontalOverflow = HorizontalWrapMode.Overflow;
                keep(iconImage, text);
                var button = row.gameObject.AddComponent<Button>();
                button.targetGraphic = hit;
                var colors = button.colors;
                colors.normalColor = Color.clear;
                colors.highlightedColor = WithAlpha(Cyan, 0.12f);
                colors.pressedColor = WithAlpha(Cyan, 0.22f);
                colors.selectedColor = Color.clear;
                button.colors = colors;
                button.onClick.AddListener(() => click());
            }
            _morePop.SetActive(false);
        }

        void ShowMorePop(bool on)
        {
            _morePop.SetActive(on);
            if (on) RefreshMorePop();
        }

        // メニューの行の文字（Refresh から呼ぶ）
        void RefreshMorePop()
        {
            var c = _conversation;
            var connected = c.Status == CielConversation.State.Connected;
            if (_moreImageText != null)
            {
                _moreImageText.text = connected ? "画像を見せる" : "画像を見せる（つないでから）";
                _moreImageText.color = connected ? TextMain : TextSub;
                _moreImageIcon.color = WithAlpha(Hex(0xE6F8FF), connected ? 1f : 0.4f);
            }
            var rec = c.MinutesOn;
            _moreSummaryText.text = rec ? "まとめ（記録中）" : "まとめ（議事録）";
            _moreSummaryText.color = rec ? Amber : TextMain;
            _moreSummaryIcon.color = rec ? Amber : Hex(0xE6F8FF);
        }

        // ＋のボタンの文字：画像を送ったあとの様子（数秒）、議事録をとっているあいだは「記録中」、ふだんは「ほか」
        static string MoreLabel(CielConversation c, float now)
        {
            var age = now - c.ImageStateAt;
            if (c.ImageState == "sending" && age < 15f) return "送っています";
            if (c.ImageState == "received" && age < 6f) return "見せました";
            if (c.ImageState == "failed" && age < 6f)
                return c.ImageReason == "too_large" ? "大きすぎます" : c.ImageReason == "not_image" ? "画像ではありません"
                    : c.ImageReason == "unavailable" ? "見られません" : "送れません";
            return c.MinutesOn ? "記録中" : "ほか";
        }
    }
}
