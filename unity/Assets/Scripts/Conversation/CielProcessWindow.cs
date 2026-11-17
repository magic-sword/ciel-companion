using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.Conversation
{
    // 固定の実行構造を実状態で強調する。モデル・会話・音声を追加起動しない。
    public sealed class CielProcessWindow : MonoBehaviour
    {
        public const int Layer = 27;
        public const string Title = "CIEL Broadcast 会話グラフ";
        public CielStreamWindow Output { get; private set; }
        CielConversation _conversation;
        CielDisplaySurface _surface;
        Font _font;
        Text _status, _continuation, _audio;
        readonly Dictionary<string, Image> _nodes = new();
        static readonly Color Ink = new(0.94f, 0.98f, 1), Cyan = new(.5f, .91f, 1), Back = new(.027f, .11f, .15f);

        void Awake()
        {
            _conversation = FindAnyObjectByType<CielConversation>();
            _surface = new CielDisplaySurface(transform, "Process Source Camera", "Process Graph Output", "ProcessGraphCanvas",
                Layer, -22, Back, Title, "CielProcessGraphWindow", "ciel.processGraph", new Vector2Int(1552, 873));
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
            _surface.SetLayer(go); Show(null, false, 0);
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
            _surface.BindCamera();
        }
    }
}
