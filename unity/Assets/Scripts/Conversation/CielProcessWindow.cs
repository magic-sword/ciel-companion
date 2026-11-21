using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    // 固定の実行構造を実状態で強調する。モデル・会話・音声を追加起動しない。
    // 下の帯（Y=873〜1293）に、心の考え（mind.ideas：話したいこと・点・話したか）を映す。窓は1つのまま、
    // OBSでは同じウィンドウキャプチャを複製して切り抜き、グラフと心の欄を場面ごとに別の位置へ置く。
    public sealed class CielProcessWindow : MonoBehaviour
    {
        public const int Layer = 27;
        public const string Title = "CIEL Broadcast 会話グラフ";
        public const int GraphHeight = 873, MindHeight = 420;
        const int MindCards = 3, MindIdeas = 2, BarWidth = 300;
        public CielStreamWindow Output { get; private set; }
        CielConversation _conversation;
        CielDisplaySurface _surface;
        Font _font;
        Text _status, _continuation, _audio;
        readonly Dictionary<string, Image> _nodes = new();
        Text _mindTitle, _mindRule;
        MindSlot[] _mind;
        int _mindShown = -1;
        sealed class IdeaSlot { public Text line, score, reasons; public RectTransform bar, fill, mark; }
        sealed class MindSlot { public GameObject root; public Text heard, phase; public IdeaSlot[] ideas; }
        static readonly Color Ink = new(0.94f, 0.98f, 1), Cyan = new(.5f, .91f, 1), Back = new(.027f, .11f, .15f);

        void Awake()
        {
            _conversation = FindAnyObjectByType<CielConversation>();
            // 心の欄を足す前の大きさ（1552×873）で覚えていた窓は、新しい大きさで開き直す
            if (PlayerPrefs.GetInt("ciel.processGraph.height", 0) == GraphHeight)
            { PlayerPrefs.DeleteKey("ciel.processGraph.width"); PlayerPrefs.DeleteKey("ciel.processGraph.height"); }
            _surface = new CielDisplaySurface(transform, "Process Source Camera", "Process Graph Output", "ProcessGraphCanvas",
                Layer, -22, Back, Title, "CielProcessGraphWindow", "ciel.processGraph", new Vector2Int(1552, GraphHeight + MindHeight));
            Output = _surface.Output;
            var go = _surface.Canvas.gameObject;
            var root = (RectTransform)go.transform;
            _font = Font.CreateDynamicFontFromOSFont(new[] { "Yu Gothic UI", "Meiryo", "Noto Sans CJK JP" }, 64);
            Label(root, "シエルの会話・実行ループ", 40, 30, 960, 50, 34);
            _status = Label(root, "状態の通知を待っています", 40, 86, 960, 50, 24);
            // 右側はOBSのゲーム小窓・シエルと重なる領域。重要な節はX<1000へ収める。
            Edge(root,new(288,258),new(378,258)); Edge(root,new(618,258),new(708,258));
            // 出力には無言も含む。継続なら判断へ戻り、待機なら外部入力へ戻る。
            Path(root,new(848,204),new(848,170),new(168,170),new(168,204));
            Path(root,new(988,258),new(1010,258),new(1010,668),new(988,668));
            Path(root,new(848,614),new(848,590),new(1018,590),new(1018,148),new(498,148),new(498,204));
            Path(root,new(448,312),new(448,370),new(188,370),new(188,434));
            Path(root,new(548,312),new(548,434));
            Path(root,new(188,542),new(188,574),new(848,574),new(848,542));
            Edge(root,new(658,488),new(708,488));
            Path(root,new(848,434),new(848,350),new(598,350),new(598,312));
            Label(root,"待つ",260,135,100,30,20); Label(root,"続ける",900,562,100,30,20);
            Node(root,"idle","待機","発言・結果・出来事",48,204,240);
            Node(root,"deciding","判断","返事・行動を選ぶ",378,204,240);
            Node(root,"finished","出力を確定","話す／無言で進む",708,204,280);
            Node(root,"loading","機能ロード","必要な定義を取得",48,434,280);
            Node(root,"calling","操作を呼ぶ","結果を待つ",378,434,280);
            Node(root,"reviewing","結果確認","判断へ戻す",708,434,280);
            Node(root,"continuing","続きの判断","話す・行動・考える",708,614,280);
            Node(root,"cancelled","中断","次の入力へ",48,614,240);
            Node(root,"failed","エラー","処理を停止",378,614,240);
            _continuation = Label(root,"",48,774,950,44,25);
            _audio = Label(root,"",48,820,950,38,23);
            BuildMind(root);
            _surface.SetLayer(go); Show(null, false, 0);
        }

        void BuildMind(RectTransform root)
        {
            const float y0 = GraphHeight + 16;
            Box(root, "MindRule", 40, GraphHeight + 2, 1472, 2).gameObject.AddComponent<Image>().color = new Color(.38f, .53f, .58f);
            _mindTitle = Label(root, "シエルの心：話したいこと", 40, y0, 900, 44, 30);
            _mindRule = Label(root, "", 900, y0 + 6, 612, 36, 22);
            _mindRule.alignment = TextAnchor.UpperRight;
            _mind = new MindSlot[MindCards];
            for (int k = 0; k < MindCards; k++)
            {
                var card = Box(root, "MindCard", 40 + k * 500, y0 + 56, 472, 332);
                card.gameObject.AddComponent<Image>().color = new Color(.06f, .17f, .23f);
                var slot = new MindSlot { root = card.gameObject, ideas = new IdeaSlot[MindIdeas] };
                slot.heard = Label(card, "", 16, 12, 440, 34, 24);
                slot.phase = Label(card, "", 16, 48, 440, 30, 22);
                for (int j = 0; j < MindIdeas; j++)
                {
                    float top = 90 + j * 116;
                    var idea = new IdeaSlot { line = Label(card, "", 16, top, 440, 34, 24) };
                    idea.bar = Box(card, "Bar", 16, top + 44, BarWidth, 14);
                    idea.bar.gameObject.AddComponent<Image>().color = new Color(.12f, .26f, .32f);
                    idea.fill = Box(idea.bar, "Fill", 0, 0, 0, 14);
                    idea.fill.gameObject.AddComponent<Image>();
                    idea.mark = Box(idea.bar, "Rule", 0, -5, 3, 24);
                    idea.mark.gameObject.AddComponent<Image>().color = new Color(1, .77f, .42f);
                    idea.score = Label(card, "", 16 + BarWidth + 14, top + 36, 440 - BarWidth - 14, 30, 22);
                    idea.reasons = Label(card, "", 16, top + 66, 440, 30, 20);
                    slot.ideas[j] = idea;
                }
                _mind[k] = slot;
            }
        }

        // 1〜5 の点を棒の長さに
        static float BarAt(float level) => Mathf.Clamp01((level - 1) / 4f) * BarWidth;

        public void ShowMind(CielConversation.MindIdeasState m, bool connected)
        {
            int key = !connected || m == null ? (connected ? 1 : 0) : m.revision * 4 + (CielMindPresentation.ShowText(m) ? 2 : 3);
            if (key == _mindShown) return;
            _mindShown = key;
            var cards = connected && m != null ? m.cards : System.Array.Empty<CielConversation.MindCard>();
            bool text = CielMindPresentation.ShowText(m);
            float rule = m != null && m.threshold > 0 ? m.threshold : -1;
            _mindTitle.text = !connected ? "シエルの心：会話に未接続" : m == null ? "シエルの心：考えの知らせを待っています"
                : cards.Length == 0 ? "シエルの心：まだ考えていません" : "シエルの心：話したいこと";
            _mindRule.text = m == null ? "" : (m.speak && rule > 0 ? $"自分から話す基準 {rule:0.0}（超えたら話す）" : "自分から話す：切")
                + (text ? "" : "　文は隠しています");
            for (int k = 0; k < MindCards; k++)
            {
                var slot = _mind[k];
                var c = k < cards.Length ? cards[k] : null;
                slot.root.SetActive(c != null);
                if (c == null) continue;
                slot.heard.text = text && !string.IsNullOrEmpty(c.heard) ? "「" + c.heard + "」" : "相手の発言";
                slot.phase.text = "● " + CielMindPresentation.Phase(c) + (c.ms > 0 ? $"（{c.ms / 1000f:0.0}秒で考えた）" : "");
                slot.phase.color = CielMindPresentation.Tone(c.phase);
                var ideas = c.ideas ?? System.Array.Empty<CielConversation.MindIdea>();
                for (int j = 0; j < MindIdeas; j++)
                {
                    var s = slot.ideas[j];
                    var i = j < ideas.Length ? ideas[j] : null;
                    s.line.gameObject.SetActive(i != null); s.bar.gameObject.SetActive(i != null);
                    s.score.gameObject.SetActive(i != null); s.reasons.gameObject.SetActive(i != null);
                    if (i == null) continue;
                    bool chosen = j == c.chosen;
                    s.line.text = (chosen ? "▶ " : "　 ") + CielMindPresentation.Kind(i.kind) + "　" + (text ? i.text : "（文は隠しています）");
                    s.line.color = chosen ? Ink : new Color(.72f, .82f, .87f);
                    s.fill.sizeDelta = new Vector2(BarAt(i.level), 14);
                    s.fill.GetComponent<Image>().color = rule > 0 && i.level > rule ? new Color(1, .77f, .42f) : Cyan;
                    s.mark.gameObject.SetActive(rule > 0);
                    s.mark.anchoredPosition = new Vector2(BarAt(rule), 5);
                    s.score.text = $"{i.level:0.0}点";   // 書き出し確率で重みを付けた点（取れなければ書いた点）
                    s.reasons.text = text ? "＋" + i.pro + "　－" + i.con : "";
                }
            }
        }

        static RectTransform Box(Transform parent,string name,float x,float y,float w,float h)
        {
            var go=new GameObject(name,typeof(RectTransform)); go.transform.SetParent(parent,false);
            var r=(RectTransform)go.transform; r.anchorMin=r.anchorMax=r.pivot=new Vector2(0,1);
            r.anchoredPosition=new Vector2(x,-y); r.sizeDelta=new Vector2(w,h); return r;
        }
        Text Label(Transform parent,string value,float x,float y,float w,float h,int size)
        {
            var t=Box(parent,"Label",x,y,w,h).gameObject.AddComponent<Text>();
            t.font=_font;t.fontSize=size;t.color=Ink;t.text=value;t.supportRichText=false;t.raycastTarget=false;
            t.resizeTextForBestFit=true;t.resizeTextMinSize=size-3;t.resizeTextMaxSize=size;return t;
        }
        void Node(Transform root,string id,string title,string subtitle,float x,float y,float w)
        {
            var box=Box(root,id,x,y,w,108);var fill=box.gameObject.AddComponent<Image>();
            _nodes[id]=fill; Label(box,title,20,16,w-36,44,32);Label(box,subtitle,20,65,w-36,32,23);
        }
        static void Edge(Transform parent,Vector2 a,Vector2 b,bool arrow=true)
        {
            var d=new Vector2(b.x-a.x,a.y-b.y);var r=Box(parent,"Edge",a.x,a.y,d.magnitude,3);
            r.pivot=new Vector2(0,.5f);r.localRotation=Quaternion.Euler(0,0,Mathf.Atan2(d.y,d.x)*Mathf.Rad2Deg);
            r.gameObject.AddComponent<Image>().color=new Color(.38f,.53f,.58f);
            if(!arrow)return;
            var back=(a-b).normalized*14;
            var normal=new Vector2(-back.y,back.x)*.5f;
            Edge(parent,b,b+back+normal,false);Edge(parent,b,b+back-normal,false);
        }
        static void Path(Transform root,params Vector2[] points)
        { for(int i=1;i<points.Length;i++)Edge(root,points[i-1],points[i],i==points.Length-1); }
        public void Show(CielConversation.ActivityState state,bool connected,float age)
        {
            bool fresh=connected&&CielActivityPresentation.Fresh(state,age);
            string phase=fresh?CielActivityPresentation.Position(state):null;
            foreach(var pair in _nodes)pair.Value.color=pair.Key==phase?new Color(.07f,.37f,.42f):new Color(.06f,.17f,.23f);
            // 色だけでなく現在の処理名を上部に表示する。
            _status.text=!connected?"会話に未接続":!fresh?"最新の状態を確認できません・現在位置の強調を停止":"● "+CielActivityPresentation.Continuation(state)+" ／ "+CielActivityPresentation.Decision(state);
            _status.color=fresh?Cyan:new Color(1,.77f,.42f);
            _continuation.text=fresh?CielActivityPresentation.Setting(state):"会話の進行：状態未確認";
            _audio.text=fresh?"音声："+CielActivityPresentation.Audio(state):"";
        }
        void Update()
        {
            if(_conversation!=null)Show(_conversation.Activity,_conversation.Status==CielConversation.State.Connected,Time.unscaledTime-_conversation.ActivityAt);
            if(_conversation!=null)ShowMind(_conversation.Mind,_conversation.Status==CielConversation.State.Connected);
            _surface.BindCamera();
        }
    }
}
