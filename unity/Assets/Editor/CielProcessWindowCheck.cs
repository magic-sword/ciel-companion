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
            state.decision.phase="finished";state.continuation.phase="waiting";
            window.Show(state,true,0);Render(camera,"process-speaking-waiting");
            window.Show(state,true,7);
            bool stale=false;foreach(var t in go.GetComponentsInChildren<Text>())stale|=t.text.Contains("強調を停止");
            if(!stale)throw new Exception("Stale graph must be explicit");
            Render(camera,"process-stale");
            window.Show(state,false,0);
            bool disconnected=false;foreach(var t in go.GetComponentsInChildren<Text>())disconnected|=t.text=="会話に未接続";
            if(!disconnected)throw new Exception("Disconnected graph");
            CielPlanWindowCheck.Run();
            CielAudienceCardCheck.Run();
            CielBroadcastNoticeCheck.Run();
            Debug.Log("CIEL_PROCESS_WINDOW_CHECK_OK 11 states/isolation plus plan and audience checks");
        }
        static void Render(Camera camera,string name)
        {
            if(SystemInfo.graphicsDeviceType==UnityEngine.Rendering.GraphicsDeviceType.Null)throw new Exception("Rendering unavailable");
            var rt=new RenderTexture(1552,873,24);camera.targetTexture=rt;camera.aspect=1552f/873;
            Canvas.ForceUpdateCanvases();camera.Render();RenderTexture.active=rt;
            var image=new Texture2D(1552,873,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,1552,873),0,0);image.Apply();
            var dir=Path.GetFullPath(Path.Combine(Application.dataPath,"../../.local/app-refactor"));Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir,name+".png"),image.EncodeToPNG());
            RenderTexture.active=null;camera.targetTexture=null;UnityEngine.Object.DestroyImmediate(image);rt.Release();UnityEngine.Object.DestroyImmediate(rt);
        }
        public static void VerifyAndBuild(){Run();Ciel.Companion.Editor.CielBuild.WindowsAll();}
    }
}
