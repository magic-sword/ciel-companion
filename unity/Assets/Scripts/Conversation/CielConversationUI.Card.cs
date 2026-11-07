// 会話の画面（CielConversationUI）のうち、シエルが画面に出すカード（アプリの道具 app_show_card。CielConversation.App.cs）。
// シエルの顔にかからないよう、下のマイクの上（胸の前）に、題と本文を CardSeconds 秒だけ出す。タップで閉じる。新しいカードが届いたら替える。
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    partial class CielConversationUI
    {
        const float CardSeconds = 12f;
        GameObject _card;
        Text _cardTitle, _cardBody;
        int _cardRevision = -1;

        void BuildCard(RectTransform root)
        {
            var panel = Rect("Card", root, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 196), new Vector2(330, 0));
            Rounded(panel, SheetColor, 16, raycast: true);
            var layout = panel.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.spacing = 6;
            layout.padding = new RectOffset(16, 16, 12, 14);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            panel.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            _cardTitle = Txt("Title", panel, 15, Cyan, TextAnchor.UpperLeft, true);
            _cardBody = Txt("Body", panel, 13, TextMain, TextAnchor.UpperLeft);
            _cardBody.horizontalOverflow = HorizontalWrapMode.Wrap;
            var button = panel.gameObject.AddComponent<Button>();
            button.targetGraphic = panel.GetComponent<Graphic>();
            button.onClick.AddListener(() => _conversation.CloseCard());
            _card = panel.gameObject;
            _card.SetActive(false);
        }

        // 「棒 2 本」の空白で改行されないよう、改行しない空白にする（日本語は字の切れ目で折り返す）
        static string KeepTogether(string s) => (s ?? "").Replace(' ', (char)0x00A0);

        void UpdateCard(float now)
        {
            var c = _conversation.Card;
            if (c != null && now - c.At > CardSeconds)
            {
                _conversation.CloseCard();
                c = null;
            }
            if (c == null)
            {
                if (_card.activeSelf) _card.SetActive(false);
                return;
            }
            if (_cardRevision != _conversation.CardRevision)
            {
                _cardRevision = _conversation.CardRevision;
                _cardTitle.text = c.Title;
                _cardTitle.gameObject.SetActive(c.Title != "");
                _cardBody.text = KeepTogether(c.Body);
                _cardBody.gameObject.SetActive(c.Body != "");
            }
            if (!_card.activeSelf) _card.SetActive(true);
        }
    }
}
