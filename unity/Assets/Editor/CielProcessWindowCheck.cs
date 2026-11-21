using System;
using System.IO;
using System.Reflection;
using Ciel.Conversation;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.EditorTools
{
    public static class CielProcessWindowCheck
    {
        public static void Run()
        {
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var main=new GameObject("Main Camera",typeof(Camera));main.tag="MainCamera";
            var go=new GameObject("Process Check",typeof(CielProcessWindow));
            var window=go.GetComponent<CielProcessWindow>();
            typeof(CielProcessWindow).GetMethod("Awake",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(window,null);
            var camera=go.transform.Find("Process Source Camera").GetComponent<Camera>();
            if(camera.cullingMask != 1<<CielProcessWindow.Layer || camera.GetComponent<AudioListener>()!=null
                || (main.GetComponent<Camera>().cullingMask & (1<<CielProcessWindow.Layer))!=0)throw new Exception("Process camera isolation");
            var state=new CielConversation.ActivityState {v=3,valid_for_s=6,
                decision=new CielConversation.ActivityController {phase="calling",step=2},
                continuation=new CielConversation.ActivityContinuation {enabled=true,phase="waiting"}};
            foreach(var phase in new[]{"idle","deciding","loading","calling","reviewing","finished","cancelled","failed"})
            {
                state.decision.phase=phase;state.continuation.phase=phase=="idle"?"waiting":"responding";window.Show(state,true,0);
                Render(camera,"process-"+phase);
            }
            state.decision.phase="deciding"; state.continuation.phase="continuing"; state.mind="speaking";
            window.Show(state,true,0);Render(camera,"process-continuing");
            state.mind="listening";
            window.Show(state,true,0);Render(camera,"process-silent-continuing");
            var silent=CielAudienceCardState.From(null,state,true,false);
            if(!silent.heading.Contains("続きの判断"))throw new Exception("Silent continuation card");
            state.decision.phase="finished";state.continuation.phase="waiting";
            state.mind="speaking";
            window.Show(state,true,0);Render(camera,"process-speaking-waiting");
            window.Show(state,true,7);
            bool stale=false;foreach(var t in go.GetComponentsInChildren<Text>())stale|=t.text.Contains("強調を停止");
            if(!stale)throw new Exception("Stale graph must be explicit");
            Render(camera,"process-stale");
            window.Show(state,false,0);
            bool disconnected=false;foreach(var t in go.GetComponentsInChildren<Text>())disconnected|=t.text=="会話に未接続";
            if(!disconnected)throw new Exception("Disconnected graph");
            CheckMind(window,go,camera);
            CielPlanWindowCheck.Run();
            CielAudienceCardCheck.Run();
            CielBroadcastNoticeCheck.Run();
            Debug.Log("CIEL_PROCESS_WINDOW_CHECK_OK 11 states/isolation, mind panel plus plan and audience checks");
        }
        // 心の欄：考えの段・点・基準・話したか。ひとり以外では文を隠す
        static void CheckMind(CielProcessWindow window,GameObject go,Camera camera)
        {
            CielConversation.MindIdea Idea(string kind,string text,string pro,string con,int score,float level)=>
                new CielConversation.MindIdea{kind=kind,text=text,pro=pro,con=con,score=score,weighted=level,level=level};
            var mind=new CielConversation.MindIdeasState{type="mind.ideas",v=1,stream_id="check",revision=7,presence="solo",speak=true,threshold=3.5f,
                cards=new[]{
                    new CielConversation.MindCard{id=3,turn=9,heard="夜になる前に何を準備したらいい？",phase="spoken",ms=6200,chosen=0,
                        ideas=new[]{Idea("suggest","丸石で小さな家を作ろう","役に立つ","話がそれる",4,4.12f),Idea("ask","松明はいくつあるかな","次が決まる","しつこい",3,2.91f)}},
                    new CielConversation.MindCard{id=2,turn=7,heard="鎖ってどうやって作るの？",phase="dropped",reason="repeat",ms=5800,chosen=0,
                        ideas=new[]{Idea("recall","前にも鎖を作ったね","思い出せる","返事と同じ",4,3.86f)}},
                    new CielConversation.MindCard{id=1,turn=5,heard="こんにちは",phase="none",ms=3100,chosen=-1,ideas=new CielConversation.MindIdea[0]}}};
            window.ShowMind(mind,true);Render(camera,"process-mind");
            bool shown=false;foreach(var t in go.GetComponentsInChildren<Text>())shown|=t.text.Contains("丸石で小さな家");
            if(!shown)throw new Exception("Mind idea text");
            mind.presence="close";mind.revision=8;mind.cards[0].phase="thinking";mind.cards[0].ms=0;
            window.ShowMind(mind,true);Render(camera,"process-mind-hidden");
            foreach(var t in go.GetComponentsInChildren<Text>())if(t.text.Contains("丸石")||t.text.Contains("夜になる前"))throw new Exception("Mind text must be hidden with others present");
            window.ShowMind(null,true);
            bool waiting=false;foreach(var t in go.GetComponentsInChildren<Text>())waiting|=t.text.Contains("考えの知らせを待っています");
            if(!waiting)throw new Exception("Mind waiting");
        }
        const int W=1552,H=CielProcessWindow.GraphHeight+CielProcessWindow.MindHeight;
        static void Render(Camera camera,string name)
        {
            if(SystemInfo.graphicsDeviceType==UnityEngine.Rendering.GraphicsDeviceType.Null)throw new Exception("Rendering unavailable");
            var rt=new RenderTexture(W,H,24);camera.targetTexture=rt;camera.aspect=(float)W/H;
            Canvas.ForceUpdateCanvases();camera.Render();RenderTexture.active=rt;
            var image=new Texture2D(W,H,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,W,H),0,0);image.Apply();
            var dir=Path.GetFullPath(Path.Combine(Application.dataPath,"../../.local/app-refactor"));Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir,name+".png"),image.EncodeToPNG());
            RenderTexture.active=null;camera.targetTexture=null;UnityEngine.Object.DestroyImmediate(image);rt.Release();UnityEngine.Object.DestroyImmediate(rt);
        }
        public static void VerifyAndBuild(){Run();Ciel.Companion.Editor.CielBuild.WindowsAll();}
    }
}
