// Exercise production C# state/presentation without Unity native code or a license.
// Stubs cover time, JSON and transport only; Editor checks cover Unity's real parser/rendering.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Ciel.Conversation;

namespace UnityEngine
{
    public static class Time { public static float unscaledTime = 100; }
    public static class Debug { public static void LogWarning(object message) {} }
    public static class JsonUtility
    {
        static readonly JsonSerializerOptions Options = new JsonSerializerOptions {
            IncludeFields = true, IgnoreReadOnlyProperties = true
        };
        public static T FromJson<T>(string json) => JsonSerializer.Deserialize<T>(json, Options);
        public static string ToJson(object value) => JsonSerializer.Serialize(value, value.GetType(), Options);
    }
}
namespace Ciel.Conversation
{
    public partial class CielConversation
    {
        public enum State { Connected }
        public State Status = State.Connected;
        public Action Changed;
        public class Participant
        {
            public readonly List<string> sent = new List<string>();
            public void PublishData(byte[] data, bool reliable, string topic) => sent.Add(Encoding.UTF8.GetString(data));
        }
        public class Room { public Participant LocalParticipant = new Participant(); }
        public Room _room = new Room();
    }
}
class Program
{
    static int checks;
    static void Check(bool ok, string name) { if (!ok) throw new Exception(name); checks++; }
    static void Receive(CielConversation c, string json) => typeof(CielConversation).GetMethod("OnGoalData", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(c, new object[] { Encoding.UTF8.GetBytes(json) });
    static CielConversation.GoalState Work() => new CielConversation.GoalState {
        v=2, type="goal.state", stream_id="stream", revision=1, confirmed=true, valid_for_ms=10000, has_task=true,
        receivedAt=UnityEngine.Time.unscaledTime,
        task=new CielConversation.WorkInfo { session="server", task_id="task", revision=1,
            state="running", title="石のツルハシ", can_stop=true, remaining_known=true, remaining_ms=20000 }
    };
    static void Main()
    {
        var c = new CielConversation();
        var g = Work();
        Receive(c, UnityEngine.JsonUtility.ToJson(g));
        Check(c.Goal.HasGoal && c.Goal.Fresh, "receive v2");
        var shown = c.Goal;
        c.SendGoalControl("stop", shown);
        Check(c._room.LocalParticipant.sent.Count == 1, "targeted stop sent");
        using(var control=JsonDocument.Parse(c._room.LocalParticipant.sent[0])) {
            Check(control.RootElement.GetProperty("v").GetInt32()==2 && control.RootElement.GetProperty("task_id").GetString()=="task", "control identity");
        }
        g.revision=2; g.task.task_id="replacement"; Receive(c, UnityEngine.JsonUtility.ToJson(g));
        c.SendGoalControl("stop", shown);
        Check(c._room.LocalParticipant.sent.Count == 1, "old displayed target cannot stop replacement");
        g.revision=1; Receive(c, UnityEngine.JsonUtility.ToJson(g));
        Check(c.Goal.revision==2, "out of order rejected");
        g.stream_id="new"; Receive(c, UnityEngine.JsonUtility.ToJson(g));
        g.stream_id="stream"; g.revision=99; Receive(c, UnityEngine.JsonUtility.ToJson(g));
        Check(c.Goal.stream_id=="new", "retired stream rejected");
        var labels = new HashSet<string>();
        g=Work();
        foreach(var phase in new[] {"accepted","running","needs_decision","cancelling","succeeded","failed","cancelled"}) {
            g.task.state=phase;
            var p=CielWorkPresentation.From(g);
            Check(p.phase==phase, "preserve "+phase);
            Check(!p.Summary.Contains("0/0"), "no steps "+phase);
            labels.Add(p.status);
        }
        Check(labels.Count==7, "all seven states distinct");
        g.task.state="needs_decision"; g.task.decision_id="decision"; g.task.can_retry=true;
        Check(CielWorkPresentation.From(g).canRetry, "fresh decision retry");
        UnityEngine.Time.unscaledTime+=11;
        var stale=CielWorkPresentation.From(g);
        Check(stale.phase=="unknown" && stale.canStop && !stale.canRetry && stale.budget=="", "expired lease");
        g.receivedAt=UnityEngine.Time.unscaledTime;
        Check(CielWorkPresentation.From(g).canRetry, "confirmation recovers");
        g.task.state="cancelling";
        Check(!CielWorkPresentation.From(g).canRetry && !CielWorkPresentation.From(g).canStop, "no restarting cancellation");
        g.task.state="succeeded"; g.receivedAt-=11;
        Check(CielWorkPresentation.From(g).phase=="succeeded", "terminal remains confirmed historical fact");
        g=Work();
        var a=new CielConversation.ActivityState { mind="speaking", detail_version=1,
            body=new CielConversation.ActivityBody { version=1, phase="running", title="採集中" } };
        var card=CielAudienceCardState.From(g,a,true,false);
        Check(card.phase=="running" && card.conversation.Contains("話しています"), "work and speech coexist");
        Check(card.fraction < 0 && card.progress.Contains("予算"), "budget not percent");
        Check(CielAudienceCardState.From(g,a,false,false).phase=="disconnected", "disconnected explicit");
        a.mind="thinking"; a.thinking_origin="comment";
        Check(CielAudienceCardState.From(g,a,true,false).conversation.Contains("コメント"), "comment reaction parallel");
        g.task.state="needs_decision"; g.task.decision_message="材料がありません";
        Check(CielAudienceCardState.From(g,a,true,false).current.Contains("材料"), "decision evidence");
        g.task.state="succeeded";
        a=new CielConversation.ActivityState {mind="listening", detail_version=1, body=new CielConversation.ActivityBody {version=1,phase="idle"}};
        Check(CielAudienceCardState.From(g,a,true,true).heading.Contains("処理終了"), "processing completion does not claim objective achievement");
        Check(CielAudienceCardState.From(g,a,true,false).phase=="idle", "completion expires");
        Receive(c, "{\"v\":1,\"type\":\"goal.state\"}");
        Check(c.Goal.protocolError && !CielWorkPresentation.From(c.Goal).canRetry, "old version unknown");
        Check(!CielWorkPresentation.From(new CielConversation.GoalState {v=2, confirmed=true}).visible, "empty state has no phantom task");
        Console.WriteLine($"WORK_DISPLAY_CHECK_OK {checks} checks (production C# with time/JSON/transport stubs)");
    }
}
