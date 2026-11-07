// 配信版の映像に載せる札。日常版の目的パネルから、配信のカメラ・表示設定を分離する。
using System.Text;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const string StreamGoalPrefKey = "ciel.streamGoal";
        const int StreamStepsShown = 5;
        // 配信用の札
        Canvas _streamGoalCanvas;
        RectTransform _streamGoalCard;
        Text _streamGoalText;
        Image _streamGoalSwitch, _streamGoalKnob;

        bool StreamGoalOn => PlayerPrefs.GetInt(StreamGoalPrefKey, _profile != null && _profile.showStatusOnOutput ? 1 : 0) == 1;

        void BuildStreamGoal()
        {
            if (_stream == null) return;
            var go = new GameObject("StreamGoalCanvas", typeof(Canvas), typeof(CanvasScaler));
            go.transform.SetParent(transform, false);
            _streamGoalCanvas = go.GetComponent<Canvas>();
            _streamGoalCanvas.renderMode = RenderMode.ScreenSpaceCamera;
            _streamGoalCanvas.planeDistance = 1f;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(540, 960);
            scaler.matchWidthOrHeight = 0.5f;
            var root = (RectTransform)go.transform;
            _streamGoalCard = Rect("GoalCard", root, new Vector2(0, 1), new Vector2(0, 1), new Vector2(18, -18), new Vector2(320, 100));
            Rounded(_streamGoalCard, new Color(0.03f, 0.10f, 0.17f, 0.78f), 14);
            // 縁は板と同じ角の半径にする（Edge はカプセル形なので、背の高いカードだと大きな丸になる）
            SetRadius(Img(_streamGoalCard, "circle_outline", WithAlpha(Cyan, 0.55f), child: true), 14);
            var layout = _streamGoalCard.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(14, 14, 10, 12);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            _streamGoalCard.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            _streamGoalText = Txt("Text", _streamGoalCard, 15, TextMain, TextAnchor.UpperLeft);
            _streamGoalText.supportRichText = true;
            SetLayer(go, CielStreamWindow.OverlayLayer);
            go.SetActive(false);
        }

        static void SetLayer(GameObject go, int layer)
        {
            go.layer = layer;
            foreach (Transform t in go.transform) SetLayer(t.gameObject, layer);
        }

        void BuildStreamGoalSwitch(RectTransform sec)
        {
            (_streamGoalSwitch, _streamGoalKnob) = SwitchRow(sec, "シエルの映像に、目的と処理状態を重ねる", () =>
            {
                PlayerPrefs.SetInt(StreamGoalPrefKey, StreamGoalOn ? 0 : 1);
                PlayerPrefs.Save();
                Refresh();
            });
        }

        void RefreshStreamGoalSwitch()
        {
            if (_streamGoalSwitch != null) ShowSwitch(_streamGoalSwitch, _streamGoalKnob, StreamGoalOn);
        }

        static string StreamStatusText(CielConversation.GoalState g, bool recent, string activity)
        {
            var current = string.IsNullOrEmpty(activity) ? ""
                : $"<size=13><color=#9FDDF0>{Esc(activity)}</color></size>";
            if (g != null && g.Active)
                return StreamText(g) + (current.Length > 0 ? "\n\n" + current : "");
            if (current.Length > 0) return "<size=12><color=#9FDDF0>いまのシエル</color></size>\n" + current;
            return g != null && g.HasGoal && recent ? StreamText(g) : "";
        }

        static string StreamText(CielConversation.GoalState g)
        {
            var b = new StringBuilder();
            b.Append($"<size=12><color=#9FDDF0>いまの目的・{Esc(g.goal.game_label)}</color></size>\n");
            var st = g.goal.status;
            var tail = st == "done" ? "  <color=#5BF0C8>できた！</color>" : st == "stopped" ? "  <color=#8FB3C3>やめた</color>" : "";
            b.Append($"<b>{Esc(g.goal.title)}</b>{tail}\n<size=12><color=#8FB3C3>{Esc(g.goal.by_label)}</color></size>\n");
            if (g.SubPath != null) b.Append($"<size=13><color=#9FDDF0>› 先に：{Esc(g.SubPath)}</color></size>\n");
            var steps = g.steps ?? new CielConversation.GoalStep[0];
            var (done, _, _) = Count(g);
            var skip = Mathf.Max(0, Mathf.Min(done, steps.Length - StreamStepsShown));
            if (skip > 0) b.Append($"<color=#5BF0C8>●</color> <color=#8FB3C3>済んだ段 {skip}</color>\n");
            int shown = 0;
            for (int i = 0, d = 0; i < steps.Length && shown < StreamStepsShown; i++)
            {
                if (steps[i].status == "done" && d++ < skip) continue;
                b.Append($"{Mark(steps[i].status)} {Esc(steps[i].label)}{Progress(steps[i])}\n");
                shown++;
            }
            if (!string.IsNullOrEmpty(g.attention)) b.Append($"<size=12><color=#FFC46B>止まっている：{Esc(g.attention)}</color></size>\n");
            if (g.changes != null && g.changes.Length > 0) b.Append($"<size=12><color=#CDEFFA>直した：{Esc(g.changes[g.changes.Length - 1])}</color></size>\n");
            if (g.next != null && g.next.Length > 0) b.Append($"<size=12><color=#CDEFFA>つぎ：{Esc(g.next[0])}</color></size>");
            return b.ToString().TrimEnd('\n');
        }

        void UpdateBroadcastOutput(bool connected)
        {
            var c = _conversation;
            var g = connected ? c.Goal : null;
            var recent = g != null && g.HasGoal && Time.unscaledTime - c.GoalSince < GoalEndShown;
            if (_streamGoalCanvas != null)
            {
                var a = connected ? c.Activity : null;
                var activity = a != null ? ActivityChip(c, a, activeOnly: true).text : "";
                // 目的の更新が無くても、次の直接の採集・探索や経過秒数を反映する。
                var text = StreamStatusText(g, recent, activity);
                if (_streamGoalText.text != text) _streamGoalText.text = text;
                var cam = _stream.StreamCamera;
                var on = cam != null && StreamGoalOn && text.Length > 0;
                if (on && _streamGoalCanvas.worldCamera != cam) _streamGoalCanvas.worldCamera = cam;
                if (_streamGoalCanvas.gameObject.activeSelf != on) _streamGoalCanvas.gameObject.SetActive(on);
            }
        }
    }
}
