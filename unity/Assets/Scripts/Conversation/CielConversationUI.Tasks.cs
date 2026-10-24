// 会話の画面（CielConversationUI）のうち、裏で進んでいる仕事の札（声の様子のすぐ上に並ぶ）。
// 会話の番（聞いています・考えています・話しています）はマイクの上の大きな文字にいつも 1 つだけ出し、
// 会話と並んで進む仕事（Web で調べている・まとめを更新・清書している）は、仕事ごとの札でいつも同じ場所に出す。
// 札をタップすると、その中身（調べたこと・出典のパネル、まとめのパネル）を開く。
using System;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        static readonly Color ResearchGlass = new Color(0.04f, 0.30f, 0.40f, 0.72f);

        RectTransform _tasksRow;
        (GameObject go, Text label, Image dot) _researchTask, _summaryTask;

        void BuildTasks(RectTransform root)
        {
            _tasksRow = Rect("Tasks", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0.5f), new Vector2(0, 218), new Vector2(360, 24));
            var layout = _tasksRow.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.spacing = 6;
            layout.childAlignment = TextAnchor.MiddleCenter;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            _researchTask = TaskChip("Research", ResearchGlass, Cyan, () =>
            {
                // 調べている最中のページを開く
                var results = _conversation.ResearchResults;
                var id = -1;
                for (int i = results.Count - 1; i >= 0 && id < 0; i--) if (results[i].status == "pending") id = results[i].id;
                OpenResearch(id);
            });
            _summaryTask = TaskChip("Summary", AmberGlass, Amber, () => ShowSummary(true));
        }

        (GameObject, Text, Image) TaskChip(string name, Color fill, Color edge, Action onClick)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(LayoutElement));
            go.transform.SetParent(_tasksRow, false);
            var r = (RectTransform)go.transform;
            go.GetComponent<LayoutElement>().preferredHeight = 24;
            // 背景は子に置く（札に Image があると、画像の大きさが札の幅として並べ方に伝わる）
            var bg = Img(r, "circle", fill, raycast: true, child: true);
            bg.type = Image.Type.Sliced;
            bg.gameObject.AddComponent<PillRadius>();
            Edge(r, WithAlpha(edge, 0.7f));
            var layout = go.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(9, 11, 0, 0);
            layout.spacing = 5;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var dot = new GameObject("Dot", typeof(RectTransform), typeof(LayoutElement));
            dot.transform.SetParent(r, false);
            var dotLayout = dot.GetComponent<LayoutElement>();
            dotLayout.preferredWidth = dotLayout.preferredHeight = 6;
            var dotImage = Img((RectTransform)dot.transform, "circle", edge);
            var label = Txt("Label", r, 11, TextMain, TextAnchor.MiddleLeft);
            label.supportRichText = false;
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            var button = go.AddComponent<Button>();
            button.targetGraphic = bg;
            button.onClick.AddListener(() => onClick());
            go.SetActive(false);
            return (go, label, dotImage);
        }

        // 札の出し入れと文言（Update から毎フレーム。変わったときだけ書き換える）。点は、仕事が進んでいるあいだ呼吸するように光る
        void UpdateTasks(bool connected)
        {
            var c = _conversation;
            var seconds = connected ? c.ResearchSeconds : -1f;
            SetTask(_researchTask, seconds >= 0, seconds >= 0 ? $"調べています {(int)seconds}秒" : "");
            var summarizing = connected && c.Summarizing;
            SetTask(_summaryTask, summarizing, !summarizing ? ""
                : c.Summary.updating ? $"{c.Summary.label}を更新中" : $"{c.Summary.label}を清書しています");
            var pulse = 0.45f + 0.55f * (Mathf.Sin(Time.unscaledTime * Mathf.PI * 2 / 1.4f) + 1) / 2;
            _researchTask.dot.color = WithAlpha(Cyan, pulse);
            _summaryTask.dot.color = WithAlpha(Amber, pulse);
        }

        static void SetTask((GameObject go, Text label, Image dot) task, bool on, string text)
        {
            if (task.go.activeSelf != on) task.go.SetActive(on);
            if (on && task.label.text != text) task.label.text = text;
        }
    }
}
