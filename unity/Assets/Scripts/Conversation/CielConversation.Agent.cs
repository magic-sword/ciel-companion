// 会話（CielConversation）のうち、シエルの会話サーバーが部屋にいるか。
// アプリが LiveKit の部屋に入れても、会話サーバー（自宅サーバーの server/agent）が来なければシエルは返事をしない。
// 自宅サーバーが止まったとき、画面には「つながっています」としか出ず、気づけなかった（2026-11-06）。
// 会話サーバーは部屋の参加者として入ってくる（名前が agent- で始まり、属性 lk.agent.state を持つ）ので、それで見分ける。
// つないでから AgentWaitSeconds 来ない・途中で出ていったら AgentMissing で知らせ、画面の左上に出す（タップでつなぎ直す）。
using System.Linq;
using LiveKit;
using UnityEngine;

namespace Ciel.Conversation
{
    partial class CielConversation
    {
        const float AgentWaitSeconds = 10f;   // 会話サーバーはふつう 1〜3 秒で入ってくる

        bool _agentPresent;
        bool _agentEverCame;
        float _agentWaitFrom = -1f;   // 部屋に入った時刻か、会話サーバーが出ていった時刻

        /// 会話サーバーが来ない（never）・出ていった（left）。いれば・まだ待っているあいだは空
        public string AgentMissing
        {
            get
            {
                if (Status != State.Connected || _agentPresent || _agentWaitFrom < 0) return "";
                if (Time.unscaledTime - _agentWaitFrom < AgentWaitSeconds) return "";
                return _agentEverCame ? "left" : "never";
            }
        }

        static bool IsAgent(Participant p) =>
            p != null && ((p.Identity ?? "").StartsWith("agent-") || (p.Attributes != null && p.Attributes.ContainsKey(AgentStateAttribute)));

        // 部屋に入ったとき（すでに会話サーバーがいれば、それで分かる）
        void StartAgentWatch()
        {
            _agentEverCame = false;
            _agentPresent = _room != null && _room.RemoteParticipants.Values.Any(IsAgent);
            _agentEverCame = _agentPresent;
            _agentWaitFrom = Time.unscaledTime;
        }

        void NoteAgentJoined(Participant p)
        {
            if (!IsAgent(p) || _agentPresent) return;
            _agentPresent = _agentEverCame = true;
            Debug.Log("[CielConversation] シエルの会話サーバーが部屋に入った");
            Changed?.Invoke();
        }

        void OnParticipantDisconnected(Participant p)
        {
            if (!IsAgent(p) || _room == null) return;
            _agentPresent = _room.RemoteParticipants.Values.Any(x => x != p && IsAgent(x));
            if (_agentPresent) return;
            _agentWaitFrom = Time.unscaledTime;
            Debug.LogWarning("[CielConversation] シエルの会話サーバーが部屋から出ていった");
            Changed?.Invoke();
        }

        void ResetAgentWatch() => (_agentPresent, _agentEverCame, _agentWaitFrom) = (false, false, -1f);
    }
}
