using System;
using System.Reflection;
using Ciel.Conversation;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielLocalServerSettingsCheck
    {
        public static void VerifyAndBuild()
        {
            const string urlKey="ciel.localServerUrl", modeKey="ciel.localServer";
            bool hadUrl=PlayerPrefs.HasKey(urlKey), hadMode=PlayerPrefs.HasKey(modeKey);
            string oldUrl=PlayerPrefs.GetString(urlKey);
            int oldMode=PlayerPrefs.GetInt(modeKey);
            GameObject go=null;
            var load=typeof(CielConversation).GetMethod("LoadLocalServer",BindingFlags.Instance|BindingFlags.NonPublic);
            void Check(bool ok,string name) { if(!ok)throw new Exception("Local server settings: "+name); }
            try
            {
                PlayerPrefs.DeleteKey(urlKey);PlayerPrefs.DeleteKey(modeKey);
                go=new GameObject("Local server settings check",typeof(CielConversation));
                var c=go.GetComponent<CielConversation>();
                load.Invoke(c,null);
                Check(c.LocalServerUrl==CielConversation.DefaultLocalServerUrl && !c.LocalServer,"fresh install has endpoint without changing server selection");
                PlayerPrefs.SetString(urlKey," ");load.Invoke(c,null);
                Check(c.LocalServerUrl==CielConversation.DefaultLocalServerUrl,"old empty preference uses default");
                c.SetLocalServerUrl(" http://127.0.0.1:7883/token ");c.SetLocalServer(true);
                UnityEngine.Object.DestroyImmediate(go);
                go=new GameObject("Reload settings",typeof(CielConversation));c=go.GetComponent<CielConversation>();
                load.Invoke(c,null);
                Check(c.LocalServerUrl=="http://127.0.0.1:7883/token" && c.LocalServer,"custom endpoint and selection survive recreation");
                c.SetLocalServerUrl("");load.Invoke(c,null);
                Check(c.LocalServerUrl==CielConversation.DefaultLocalServerUrl && c.LocalServer,"blank restores default and keeps selection");
                c.SetLocalServer(false);load.Invoke(c,null);
                Check(!c.LocalServer,"explicit cloud selection remains off");
                Debug.Log("CIEL_LOCAL_SERVER_SETTINGS_CHECK_OK 5");
            }
            finally
            {
                if(go!=null)UnityEngine.Object.DestroyImmediate(go);
                if(hadUrl)PlayerPrefs.SetString(urlKey,oldUrl);else PlayerPrefs.DeleteKey(urlKey);
                if(hadMode)PlayerPrefs.SetInt(modeKey,oldMode);else PlayerPrefs.DeleteKey(modeKey);
                PlayerPrefs.Save();
            }
            CielAppCompositionCheck.Run();
            Ciel.Companion.Editor.CielBuild.WindowsAll();
        }
    }
}
