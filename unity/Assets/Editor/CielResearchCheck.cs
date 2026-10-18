// Python が生成した調査パケットを Unity で受信し、出典 UI まで確認する。ネットワークには接続しない。
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using Ciel.Conversation;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Ciel.EditorTools
{
    public static class CielResearchCheck
    {
        public static void Run()
        {
            var output = Path.GetFullPath(Path.Combine(Application.dataPath, "../../.local/research-check"));
            Directory.CreateDirectory(output);
            try
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var go = new GameObject("ResearchCheck");
                var conversation = go.AddComponent<CielConversation>();
                var receive = typeof(CielConversation).GetMethod("OnResearchData", BindingFlags.Instance | BindingFlags.NonPublic);
                foreach (var line in File.ReadAllLines(Path.Combine(output, "packets.jsonl")))
                    receive.Invoke(conversation, new object[] { Encoding.UTF8.GetBytes(line) });
                var result = conversation.ResearchResults.Single();
                if (result.status != "completed" || !result.Summary.Contains("テスト本文") || result.sources.Count != 2)
                    throw new Exception("Research packet roundtrip failed");
                if (CielConversation.IsWebUrl("javascript:alert(1)") || CielConversation.IsWebUrl("file:///C:/secret"))
                    throw new Exception("Non-web links were accepted");
                var ui = go.AddComponent<CielConversationUI>();
                typeof(CielConversationUI).GetMethod("Awake", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(ui, null);
                typeof(CielConversationUI).GetMethod("Refresh", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(ui, null);
                var panel = go.GetComponentsInChildren<RectTransform>(true).Single(r => r.name == "ResearchPanel");
                panel.gameObject.SetActive(true);
                Canvas.ForceUpdateCanvases();
                var content = panel.GetComponentsInChildren<RectTransform>().Single(r => r.name == "Content");
                LayoutRebuilder.ForceRebuildLayoutImmediate(content);
                if (panel.GetComponentsInChildren<Button>().Length != 3)
                    throw new Exception("Expected close button and two source links");
                var sourceLabels = panel.GetComponentsInChildren<Text>().Where(t => t.name == "Source").ToArray();
                if (sourceLabels.Length != 2 || sourceLabels.Any(t => t.supportRichText))
                    throw new Exception("Source labels missing or rich-text enabled");
                File.WriteAllText(Path.Combine(output, "unity-check.txt"), "PASS: Python/Unity packet roundtrip, chunked text, source links, safe schemes, and source UI layout");
                Debug.Log("CIEL_RESEARCH_CHECK_DONE");
                EditorApplication.Exit(0);
            }
            catch (Exception ex)
            {
                File.WriteAllText(Path.Combine(output, "unity-check.txt"), ex.ToString());
                Debug.LogException(ex);
                EditorApplication.Exit(1);
            }
        }
    }
}
