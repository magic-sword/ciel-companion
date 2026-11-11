// Disconnect races without opening a microphone or contacting LiveKit.
using System;
using System.Collections;
using System.Reflection;
using Ciel.Conversation;
using LiveKit;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Ciel.EditorTools
{
    public static class CielMicrophoneReconnectCheck
    {
        const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
        static int _checks;
        static void Check(bool value, string name)
        {
            if (!value) throw new Exception("Microphone reconnect: " + name);
            _checks++;
        }
        static void Field(CielConversation c, string name, object value) => typeof(CielConversation).GetField(name, Private).SetValue(c, value);
        static object Call(CielConversation c, string name, params object[] args) => typeof(CielConversation).GetMethod(name, Private).Invoke(c, args);
        static void Status(CielConversation c, CielConversation.State value) => typeof(CielConversation).GetProperty("Status").SetValue(c, value);

        public static void VerifyAndBuildBroadcast()
        {
            CielAppCompositionCheck.Run();
            Ciel.Companion.Editor.CielBuild.WindowsBroadcast();
        }

        public static void Run()
        {
            _checks = 0;
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var go = new GameObject("Microphone reconnect check", typeof(CielConversation));
            var c = go.GetComponent<CielConversation>();
            try
            {
                Field(c, "_busy", true); Field(c, "_micRestarting", true); Field(c, "_recording", true);
                c.EndConversation();
                Check(!c.MicBusy && !c.MicEnabled, "disconnect clears publish and device-switch flags");
                Check(c.Status == CielConversation.State.Disconnected, "intentional disconnect stays disconnected");

                Status(c, CielConversation.State.Connected); Field(c, "_busy", true);
                var stale = (IEnumerator)Call(c, "RestartMic");
                Check(stale.MoveNext(), "old device switch waits for microphone publication");
                c.EndConversation();
                Status(c, CielConversation.State.Connected); Field(c, "_busy", true);
                Check(!stale.MoveNext(), "old switch stops instead of waiting on the replacement connection");
                Check(c.MicBusy, "old operation cannot release new connection's busy flag");
                c.EndConversation();

                Field(c, "_recording", true); Call(c, "StopRecording");
                Check(!c.MicEnabled, "missing audio device cannot leave a recording indicator");

                var oldRoom = new Room(); var newRoom = new Room();
                Field(c, "_room", newRoom); Status(c, CielConversation.State.Connected); Field(c, "_busy", true);
                Call(c, "OnRoomDisconnected", oldRoom);
                Check(c.Status == CielConversation.State.Connected && c.MicBusy, "late old-room notification does not affect new room");
                Call(c, "OnRoomDisconnected", newRoom);
                Check(c.Status == CielConversation.State.Failed && !c.MicBusy && !c.MicEnabled,
                    "unexpected disconnect releases mic and offers reconnect");
                oldRoom.Dispose();

                Field(c, "_room", new Room()); Status(c, CielConversation.State.Connecting);
                c.SetMicEnabled(true);
                Check(!c.MicBusy && !c.MicEnabled, "mic cannot start while connecting");
                c.EndConversation(); c.EndConversation();
                Check(!c.MicBusy, "repeated cleanup is safe");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
            Debug.Log("CIEL_MICROPHONE_RECONNECT_CHECK_OK " + _checks);
        }
    }
}
