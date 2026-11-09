// 会話の画面（CielConversationUI）のうち、いまのシエル（CielConversation.Activity。会話サーバーの activity.py）。
// 止まって見えるとき、心が考えているのか、道具の結果を待っているのか、体が技をしているのかを見せる（2026-11-07）。
// - 札の列に「いま」の札：いちばん大事な 1 つ（道具の結果を待っている → 体の技 → 考えている → 話している → 最近のこと）と秒数。
//   心も道具も体も動いていなくても、ゲームの体を受け持っているあいだは「待っている」で出しておく（止まっていると分かるように）。
// - タップで「いまのシエル」のパネル：心・呼んでいる道具・体・目的・最近のこと（新しいものが先）。開いているあいだ秒数を数える。
// 目的の札（CielConversationUI.Goal.cs）とは別。目的が無くても出る。
using System.Text;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const float ActivityRecent = 20f;   // 何も動いていないとき、最近のことを札に出しておく秒数
        static readonly Color ActivityGlass = new Color(0.10f, 0.16f, 0.30f, 0.72f);

        (GameObject go, Text label, Image dot) _activityTask, _bodyWorkTask;
        GameObject _activityPanel;
        Text _activityBody;
        float _activityFilled = -1f;

        void BuildActivity(RectTransform root)
        {
            _activityTask = TaskChip("Activity", ActivityGlass, Cyan, () =>
            {
                _activityPanel.SetActive(!_activityPanel.activeSelf);
                _activityFilled = -1f;
            });

            _bodyWorkTask = TaskChip("BodyWork", ActivityGlass, Cyan, () => _activityPanel.SetActive(!_activityPanel.activeSelf));

            var panel = Rect("ActivityPanel", root, Center, Center, Vector2.zero, Vector2.zero);
            panel.anchorMin = Vector2.zero;
            panel.anchorMax = Vector2.one;
            panel.offsetMin = new Vector2(16, 115);
            panel.offsetMax = new Vector2(-16, -96);
            Rounded(panel, SheetColor, 18, raycast: true);
            _activityPanel = panel.gameObject;
            var close = Rect("Close", panel, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-8, -8), new Vector2(44, 40));
            var closeButton = close.gameObject.AddComponent<Button>();
            closeButton.targetGraphic = GlassCircle(close, Cyan);
            Icon(close, "close", 14, Cyan);
            closeButton.onClick.AddListener(() => _activityPanel.SetActive(false));
            var title = Txt("Title", panel, 17, TextMain, TextAnchor.MiddleLeft, true);
            title.text = "いまのシエル";
            Place(title.rectTransform, new Vector2(0, 1), new Vector2(0, 1), new Vector2(16, -16), new Vector2(240, 30));
            _activityBody = Txt("Body", panel, 13, TextSub, TextAnchor.UpperLeft);
            _activityBody.supportRichText = true;
            _activityBody.verticalOverflow = VerticalWrapMode.Truncate;
            Stretch(_activityBody.rectTransform);
            _activityBody.rectTransform.offsetMin = new Vector2(18, 18);
            _activityBody.rectTransform.offsetMax = new Vector2(-18, -56);
            _activityPanel.SetActive(false);
        }

        void UpdateActivity(bool connected)
        {
            var c = _conversation;
            var a = connected ? c.Activity : null;
            var (text, color, show) = a != null ? ActivityChip(c, a) : ("", Idle, false);
            SetTask(_activityTask, show, text);
            var body = a?.body;
            var directBody = body != null && !string.IsNullOrEmpty(body.phase) && body.phase != "idle" && !(c.Goal?.Active ?? false);
            SetTask(_bodyWorkTask, directBody, directBody ? "体：" + body.Description : "");
            if (show)
            {
                var moving = color != Idle;
                _activityTask.dot.color = WithAlpha(color,
                    moving ? 0.45f + 0.55f * (Mathf.Sin(Time.unscaledTime * Mathf.PI * 2 / 1.0f) + 1) / 2 : 0.8f);
            }
            if (!connected && _activityPanel.activeSelf) _activityPanel.SetActive(false);
            // 開いているあいだは、0.5 秒ごとに秒数を数え直す
            if (_activityPanel.activeSelf && Time.unscaledTime - _activityFilled > 0.5f)
            {
                _activityFilled = Time.unscaledTime;
                _activityBody.text = a != null ? ActivityText(c, a) : "まだ会話サーバーから届いていません";
            }
        }

        // 改行しない空白。印と秒数のあとの空白で折り返すと、印だけが 1 行になった
        static readonly char Nb = (char)0x00A0;

        static string Sec(float s) => $"{Mathf.Max(0, (int)s)}秒";

        static string WhoName(string who) => who == "talker" ? "返事" : who == "mind" ? "判断" : "";

        // 札の文言・点の色・出すか
        static (string text, Color color, bool show) ActivityChip(CielConversation c, CielConversation.ActivityState a, bool activeOnly = false)
        {
            var conversation = CielAudienceCardState.Conversation(a, c.MicEnabled && c.UserSpeaking);
            if (!string.IsNullOrEmpty(conversation)) return ("会話：" + conversation, Mint, true);
            if (a.calls != null && a.calls.Length > 0)
                return ($"機能：{a.calls[0].label}・応答待ち {Sec(c.ActivitySeconds(a.calls[0].for_s))}", Amber, true);
            if (a.body != null && a.body.phase != "idle")
                return ($"体：{a.body.Description} {Sec(c.ActivitySeconds(a.body.for_s))}", a.body.phase == "running" ? Cyan : Amber, true);
            if (!activeOnly && a.log != null && a.log.Length > 0 && c.ActivitySeconds(a.log[0].ago) < ActivityRecent)
                return ($"いま：{a.log[0].text}", KindColor(a.log[0].kind), true);
            if (!activeOnly && c.GameLinked) return ("いま：待っている", Idle, true);
            return ("", Idle, false);
        }

        static Color KindColor(string kind) => kind == "error" ? Alert : kind == "wait" ? Amber : kind == "ok" ? Mint : Cyan;

        static string KindMark(string kind) => kind == "error" ? "<color=#FF9A8A>✕</color>" : kind == "wait" ? "<color=#FFC46B>◇</color>"
            : kind == "ok" ? "<color=#5BF0C8>✓</color>" : "<color=#7FE9FF>・</color>";

        static string ActivityText(CielConversation c, CielConversation.ActivityState a)
        {
            var b = new StringBuilder();
            string Head(string s) => $"<b><color=#9FDDF0>{s}</color></b>";
            // 心
            var mind = a.mind == "thinking" ? $"考えている（{(WhoName(a.who) != "" ? WhoName(a.who) : "返事")}）{Sec(c.ActivitySeconds(a.mind_for))}"
                : a.mind == "speaking" ? "話している" : a.mind == "listening" ? "聞いている" : "待っている";
            b.Append(Head("会話・リアクション")).Append("　").Append(Esc(mind)).Append('\n');
            b.Append(Head("裏の思考")).Append(a.background_thinking
                ? $"　自発的に考えを整理している {Sec(c.ActivitySeconds(a.background_for))}\n"
                : a.detail_version >= 1 ? "　いまは考えを生成していない\n" : "　詳しい状態はまだ確認できていない\n");
            // 呼んでいる道具
            b.Append(Head("呼んでいる道具")).Append('\n');
            if (a.calls == null || a.calls.Length == 0) b.Append("　なし\n");
            else foreach (var call in a.calls)
                b.Append($"　{Esc(call.label)}：結果を待っている {Sec(c.ActivitySeconds(call.for_s))}\n");
            // 体
            b.Append(Head("体")).Append('\n');
            var any = false;
            if (a.body != null)
            {
                b.Append($"　{Esc(a.body.Description)}（{Sec(c.ActivitySeconds(a.body.for_s))}）\n");
                if (!string.IsNullOrEmpty(a.body.next_title)) b.Append($"　次：{Esc(a.body.next_title)}\n");
                any = true;
            }
            if (!any) b.Append(c.GameLinked ? "　なにもしていない\n" : "　体とつながっていない\n");
            // 目的
            var g = c.Goal;
            if (g != null && g.Active)
            {
                b.Append(Head("作業")).Append("\n").Append(Esc(CielWorkPresentation.From(g).Summary)).Append('\n');
            }
            // 最近のこと
            b.Append(Head("最近のこと")).Append('\n');
            if (a.log == null || a.log.Length == 0) b.Append("　まだ無い\n");
            else foreach (var e in a.log)
                b.Append($"　{KindMark(e.kind)}{Nb}<color=#8FB3C3>{Sec(c.ActivitySeconds(e.ago))}前</color>{Nb}{Nb}{Esc(e.text).Replace(' ', Nb)}\n");
            return b.ToString();
        }
    }
}
