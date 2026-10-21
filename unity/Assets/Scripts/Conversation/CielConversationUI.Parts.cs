// 会話の画面（CielConversationUI）の部品を作る道具。画面の部品は、すべてここの組み合わせで作る。
// 形とアイコンの画像は Assets/Resources/CielUI（scripts/ui/make_ui_sprites.py が作る。白一色で、色はここで付ける）。
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        static readonly Vector2 Center = new Vector2(0.5f, 0.5f);
        static readonly Dictionary<string, Sprite> Sprites = new Dictionary<string, Sprite>();

        static Sprite LoadSprite(string name)
        {
            if (name == null) return null;
            if (!Sprites.TryGetValue(name, out var s))
            {
                s = Resources.Load<Sprite>("CielUI/" + name);
                if (s == null) Debug.LogWarning($"[CielConversationUI] 画像 CielUI/{name} がない");
                Sprites[name] = s;
            }
            return s;
        }

        static Color Hex(int rgb) => new Color(((rgb >> 16) & 255) / 255f, ((rgb >> 8) & 255) / 255f, (rgb & 255) / 255f);
        static Color WithAlpha(Color c, float a) => new Color(c.r, c.g, c.b, a);

        static RectTransform Rect(string name, Transform parent, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var r = (RectTransform)go.transform;
            Place(r, anchor, pivot, pos, size);
            return r;
        }

        static void Place(RectTransform r, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            r.anchorMin = r.anchorMax = anchor;
            r.pivot = pivot;
            r.anchoredPosition = pos;
            r.sizeDelta = size;
        }

        static void Stretch(RectTransform r)
        {
            r.anchorMin = Vector2.zero;
            r.anchorMax = Vector2.one;
            r.offsetMin = r.offsetMax = Vector2.zero;
        }

        /// 画像。child なら同じ大きさの子を作ってそこへ置く（1 つの部品に何枚も重ねるため）
        static Image Img(RectTransform r, string sprite, Color color, bool raycast = false, bool child = false)
        {
            if (child || r.GetComponent<Graphic>() != null)
            {
                var c = new GameObject(sprite ?? "Image", typeof(RectTransform), typeof(LayoutElement));
                c.GetComponent<LayoutElement>().ignoreLayout = true;   // 重ねる画像は、並べる対象にしない
                c.transform.SetParent(r, false);
                r = (RectTransform)c.transform;
                Stretch(r);
            }
            var img = r.gameObject.AddComponent<Image>();
            img.sprite = LoadSprite(sprite);
            img.color = color;
            img.raycastTarget = raycast;
            return img;
        }

        // 丸の画像を 9 分割で伸ばして、角の半径 radius の板にする
        static void SetRadius(Image img, float radius, float edge = 1f)
        {
            img.type = Image.Type.Sliced;
            img.fillCenter = img.sprite == null || img.sprite.name != "circle_outline";
            img.pixelsPerUnitMultiplier = 63f / Mathf.Max(radius, 1f) / edge;
        }

        static Image Rounded(RectTransform r, Color color, float radius, bool raycast = false)
        {
            var img = Img(r, "circle", color, raycast);
            SetRadius(img, radius);
            return img;
        }

        // カプセル（短い辺の半分を半径にする）
        static Image Pill(RectTransform r, Color color, bool raycast = false)
        {
            var img = Img(r, "circle", color, raycast);
            img.type = Image.Type.Sliced;
            img.gameObject.AddComponent<PillRadius>();
            return img;
        }

        // 細い光の縁（カプセルの形）
        static Image Edge(RectTransform r, Color color)
        {
            var img = Img(r, "circle_outline", color, child: true);
            img.type = Image.Type.Sliced;
            img.fillCenter = false;
            img.gameObject.AddComponent<PillRadius>();
            return img;
        }

        static Image GlassCircle(RectTransform r, Color edge)
        {
            var bg = Img(r, "circle", Glass, raycast: true);
            Edge(r, edge);
            return bg;
        }

        static Image Icon(RectTransform parent, string name, float size, Color color)
        {
            var r = Rect(name, parent, Center, Center, Vector2.zero, new Vector2(size, size));
            return Img(r, "Icons/" + name, color);
        }

        Text Txt(string name, Transform parent, int size, Color color, TextAnchor align, bool bold = false)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Text));
            go.transform.SetParent(parent, false);
            var t = go.GetComponent<Text>();
            t.font = _font;
            t.fontSize = size;
            t.fontStyle = bold ? FontStyle.Bold : FontStyle.Normal;
            t.alignment = align;
            t.color = color;
            t.raycastTarget = false;
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            return t;
        }

        // 設定の部品：縦に並ぶまとまり・決まった高さの行・見出し・注記
        static RectTransform Section(RectTransform content)
        {
            var go = new GameObject("Section", typeof(RectTransform), typeof(VerticalLayoutGroup));
            go.transform.SetParent(content, false);
            var vl = go.GetComponent<VerticalLayoutGroup>();
            vl.spacing = 12;
            vl.childControlWidth = vl.childControlHeight = true;
            vl.childForceExpandWidth = true;
            vl.childForceExpandHeight = false;
            return (RectTransform)go.transform;
        }

        static RectTransform Row(RectTransform section, float height)
        {
            var go = new GameObject("Row", typeof(RectTransform), typeof(LayoutElement));
            go.transform.SetParent(section, false);
            go.GetComponent<LayoutElement>().preferredHeight = height;
            return (RectTransform)go.transform;
        }

        Text SectionLabel(RectTransform row, string text)
        {
            var t = Txt("Label", row, 13, SectionText, TextAnchor.MiddleLeft, true);
            Stretch(t.rectTransform);
            t.text = text;
            return t;
        }

        // 文字の量に合わせた高さで並ぶ（Text が自分の高さを知らせる）
        void Note(RectTransform section, string text)
        {
            var t = Txt("Note", section, 11, TextNote, TextAnchor.UpperLeft);
            t.text = text;
        }

        // 細い光の線と六角のつまみ
        Slider BuildSlider(RectTransform r, bool vertical)
        {
            var hit = Img(r, null, Color.clear, raycast: true);
            var track = Rect("Track", r, Center, Center, Vector2.zero, Vector2.zero);
            Bar(track, vertical);
            Pill(track, WithAlpha(Cyan, 0.18f));
            var fillArea = Rect("FillArea", r, Center, Center, Vector2.zero, Vector2.zero);
            Bar(fillArea, vertical);
            var fill = Rect("Fill", fillArea, Center, Center, Vector2.zero, Vector2.zero);
            fill.sizeDelta = Vector2.zero;
            Pill(fill, CyanDeep);
            var handleArea = Rect("HandleArea", r, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(handleArea);
            if (vertical) { handleArea.offsetMin = new Vector2(0, 12); handleArea.offsetMax = new Vector2(0, -12); }
            else { handleArea.offsetMin = new Vector2(11, 0); handleArea.offsetMax = new Vector2(-11, 0); }
            // Slider は、つまみを動かす向きと直角の向きに伸ばすので、見た目の六角は真ん中に決まった大きさで置く
            var handle = Rect("Handle", handleArea, Center, Center, Vector2.zero, Vector2.zero);
            Img(Rect("Glow", handle, Center, Center, Vector2.zero, new Vector2(44, 48)), "hex_glow", WithAlpha(CyanDeep, 0.6f));
            Img(Rect("Hex", handle, Center, Center, Vector2.zero, new Vector2(22, 25)), "hex_prism", Color.white);

            var s = r.gameObject.AddComponent<Slider>();
            s.direction = vertical ? Slider.Direction.BottomToTop : Slider.Direction.LeftToRight;
            s.fillRect = fill;
            s.handleRect = handle;
            s.targetGraphic = hit;
            s.transition = Selectable.Transition.None;
            s.minValue = 0;
            s.maxValue = 1;
            handle.sizeDelta = vertical ? new Vector2(0, 25) : new Vector2(22, 0);
            return s;

            void Bar(RectTransform b, bool v)
            {
                if (v)
                {
                    b.anchorMin = new Vector2(0.5f, 0);
                    b.anchorMax = new Vector2(0.5f, 1);
                    b.offsetMin = new Vector2(-2, 12);
                    b.offsetMax = new Vector2(2, -12);
                }
                else
                {
                    b.anchorMin = new Vector2(0, 0.5f);
                    b.anchorMax = new Vector2(1, 0.5f);
                    b.offsetMin = new Vector2(11, -2);
                    b.offsetMax = new Vector2(-11, 2);
                }
            }
        }

        Dropdown NewDropdown(RectTransform root, string name)
        {
            root.name = name;
            var bg = Pill(root, Glass, raycast: true);
            Edge(root, WithAlpha(Cyan, 0.35f));
            var dd = root.gameObject.AddComponent<Dropdown>();
            dd.targetGraphic = bg;

            var label = Txt("Label", root, 13, TextMain, TextAnchor.MiddleLeft);
            Stretch(label.rectTransform);
            label.rectTransform.offsetMin = new Vector2(18, 0);
            label.rectTransform.offsetMax = new Vector2(-18, 0);
            label.horizontalOverflow = HorizontalWrapMode.Overflow;
            dd.captionText = label;

            var template = Rect("Template", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 1f), Vector2.zero, new Vector2(0, 220));
            template.anchorMin = new Vector2(0, 0);
            template.anchorMax = new Vector2(1, 0);
            Rounded(template, new Color(0.05f, 0.12f, 0.19f, 0.98f), 14, raycast: true);
            var scroll = template.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            var viewport = Rect("Viewport", template, Center, Center, Vector2.zero, Vector2.zero);
            Stretch(viewport);
            viewport.gameObject.AddComponent<RectMask2D>();
            var content = Rect("Content", viewport, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), Vector2.zero, new Vector2(0, 40));
            content.anchorMin = new Vector2(0, 1);
            content.anchorMax = new Vector2(1, 1);
            scroll.viewport = viewport;
            scroll.content = content;

            var item = Rect("Item", content, new Vector2(0.5f, 0.5f), Center, Vector2.zero, new Vector2(0, 40));
            item.anchorMin = new Vector2(0, 0.5f);
            item.anchorMax = new Vector2(1, 0.5f);
            var toggle = item.gameObject.AddComponent<Toggle>();
            var itemBg = Img(item, null, new Color(1, 1, 1, 0.06f), raycast: true, child: true);
            toggle.targetGraphic = itemBg;
            var check = Rect("Item Checkmark", item, new Vector2(0, 0.5f), Center, new Vector2(14, 0), new Vector2(8, 9));
            toggle.graphic = Img(check, "hex", Cyan);
            var itemLabel = Txt("Item Label", item, 13, TextMain, TextAnchor.MiddleLeft);
            Stretch(itemLabel.rectTransform);
            itemLabel.rectTransform.offsetMin = new Vector2(28, 0);
            itemLabel.horizontalOverflow = HorizontalWrapMode.Overflow;

            dd.template = template;
            dd.itemText = itemLabel;
            template.gameObject.SetActive(false);
            return dd;
        }

        // カプセルの中に並べた選択肢（選んだものが光る）
        void Segmented(RectTransform sec, string[] labels, Action<int> pick, List<(Image, Image, Text)> segs)
        {
            var bar = Row(sec, 46);
            Pill(bar, new Color(0.047f, 0.157f, 0.235f, 0.45f));
            Edge(bar, WithAlpha(Cyan, 0.3f));
            var hl = bar.gameObject.AddComponent<HorizontalLayoutGroup>();
            hl.padding = new RectOffset(4, 4, 4, 4);
            hl.spacing = 4;
            hl.childControlWidth = hl.childControlHeight = true;
            hl.childForceExpandWidth = hl.childForceExpandHeight = true;
            for (int i = 0; i < labels.Length; i++)
            {
                var seg = new GameObject(labels[i], typeof(RectTransform));
                seg.transform.SetParent(bar, false);
                var r = (RectTransform)seg.transform;
                var fill = Pill(r, WithAlpha(CyanDeep, 0.22f), raycast: true);
                var edge = Edge(r, Cyan);
                var label = Txt("Label", r, labels[i].Length > 4 ? 12 : 13, TextMain, TextAnchor.MiddleCenter);
                Stretch(label.rectTransform);
                label.text = labels[i];
                var b = seg.AddComponent<Button>();
                b.targetGraphic = fill;
                b.transition = Selectable.Transition.None;
                var index = i;
                b.onClick.AddListener(() => pick(index));
                segs.Add((fill, edge, label));
            }
        }

        static void ShowSelected(List<(Image fill, Image edge, Text label)> segs, int selected)
        {
            for (int i = 0; i < segs.Count; i++)
            {
                var (fill, edge, label) = segs[i];
                var sel = i == selected;
                fill.color = sel ? WithAlpha(CyanDeep, 0.22f) : Color.clear;
                edge.enabled = sel;
                label.fontStyle = sel ? FontStyle.Bold : FontStyle.Normal;
                label.color = sel ? TextMain : TextSub;
            }
        }
    }
}
