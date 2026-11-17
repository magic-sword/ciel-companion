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
        var a=new CielConversation.ActivityState { mind="speaking", v=3, valid_for_s=6,
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
        a=new CielConversation.ActivityState {mind="listening", v=3, valid_for_s=6, body=new CielConversation.ActivityBody {version=1,phase="idle"}};
        Check(CielAudienceCardState.From(g,a,true,true).heading.Contains("処理終了"), "processing completion does not claim objective achievement");
        Check(CielAudienceCardState.From(g,a,true,false).phase=="idle", "completion expires");
        Receive(c, "{\"v\":1,\"type\":\"goal.state\"}");
        Check(c.Goal.protocolError && !CielWorkPresentation.From(c.Goal).canRetry, "old version unknown");
        Check(!CielWorkPresentation.From(new CielConversation.GoalState {v=2, confirmed=true}).visible, "empty state has no phantom task");
        // plan v1: the game's graph as reported, laid out by dependency, nothing made up beside it.
        var planned = Work();
        planned.task.plan = UnityEngine.JsonUtility.FromJson<CielConversation.PlanInfo>(
            "{\"v\":1,\"plan_id\":\"p\",\"revision\":3,\"title\":\"dirt_shelter\",\"finished\":false,\"current\":[\"bed\"]," +
            "\"nodes\":[{\"id\":\"pick\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"wooden_pickaxe\",\"state\":\"done\",\"needs\":[],\"estimate_s\":-1,\"choice\":null}," +
            "{\"id\":\"bed\",\"parent\":null,\"kind\":\"obtain\",\"label\":\"white_bed ×1\",\"state\":\"running\",\"needs\":[],\"estimate_s\":120,\"choice\":null}," +
            "{\"id\":\"bed/0\",\"parent\":\"bed\",\"kind\":\"decide\",\"label\":\"white_wool ×3\",\"state\":\"waiting_choice\",\"needs\":[],\"estimate_s\":-1," +
            "\"choice\":{\"question\":\"how\",\"chosen\":null,\"options\":[{\"id\":\"kill:sheep\",\"summary\":\"\"},{\"id\":\"shear:sheep\",\"summary\":\"\"}]}}," +
            "{\"id\":\"house\",\"parent\":null,\"kind\":\"build\",\"label\":\"house\",\"state\":\"pending\",\"needs\":[\"pick\",\"bed\"],\"estimate_s\":130,\"choice\":null}]}");
        var graph = CielPlanPresentation.From(planned);
        Check(graph.visible && graph.nodes.Count == 3 && graph.columns == 2, "plan laid out by dependency");
        Check(graph.nodes.Find(n => n.id == "house").column == 1 && graph.nodes.Find(n => n.id == "bed").current, "column and current");
        Check(graph.nodes.Find(n => n.id == "bed").children.Count == 1 && graph.nodes.Find(n => n.id == "bed").estimate.Contains("120"), "children and estimate");
        Check(graph.nodes.Find(n => n.id == "pick").estimate == "", "no estimate for a done step");
        Check(graph.summary.StartsWith("選択待ち：white_wool ×3（kill:sheep / shear:sheep）") && graph.summary.Contains("完了 1/3"), "now line");
        Check(!graph.summary.Contains("%"), "no percentage");
        var plannedCard = CielAudienceCardState.From(planned, null, true, false);
        Check(plannedCard.current.StartsWith("選択待ち"), "card shows the plan's step");
        Check(!CielPlanPresentation.From(Work()).visible, "no plan, no graph");
        UnityEngine.Time.unscaledTime += 11;
        Check(CielPlanPresentation.From(planned).stale && !CielAudienceCardState.From(planned, null, true, false).current.StartsWith("選択待ち"), "stale plan is marked, not shown as now");
        UnityEngine.Time.unscaledTime -= 11;
        var live = new CielConversation.ActivityState { v=3, type="activity.state", stream_id="activity-a", revision=1,
            valid_for_s=6, mind="thinking", continuation=new CielConversation.ActivityContinuation {enabled=true,phase="waiting"},
            decision=new CielConversation.ActivityController {phase="loading", step=1}, body=new CielConversation.ActivityBody {version=1,phase="idle"} };
        void ActivityReceive(string json) => typeof(CielConversation).GetMethod("OnActivity", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(c, new object[] {Encoding.UTF8.GetBytes(json)});
        ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.ActivityFresh && CielActivityPresentation.Decision(c.Activity).Contains("読み込み"), "live controller stage");
        Check(CielAudienceCardState.Conversation(c.Activity).Contains("読み込み"), "tool phase overrides generic thinking");
        Check(CielActivityPresentation.Flow(c.Activity).Contains("● 機能ロード"), "current graph node highlighted");
        live.decision.phase="finished"; live.continuation.phase="waiting"; live.mind="speaking";
        Check(CielActivityPresentation.Position(live)=="idle" && CielActivityPresentation.Audio(live)=="話しています", "waiting generation and audio playback are independent");
        live.decision.phase="deciding"; live.continuation.phase="responding"; live.mind="thinking";
        Check(!CielAudienceCardState.Conversation(live).Contains("自発"), "ordinary response is not autonomous thought");
        live.continuation.phase="continuing";
        Check(CielActivityPresentation.Position(live)=="continuing" && CielAudienceCardState.Conversation(live).Contains("続き"), "continuation has its own node and caption");
        live.decision.phase="cancelled";
        Check(CielActivityPresentation.Position(live)=="cancelled", "interruption is not normal completion");
        live.decision.phase="failed";
        Check(CielActivityPresentation.Position(live)=="failed", "error is not normal completion");
        live.continuation.enabled=false;
        Check(CielActivityPresentation.Setting(live).Contains("無効"), "disabled continuation is explicit");
        live.decision.phase="loading";live.continuation.phase="tool_result";
        UnityEngine.Time.unscaledTime += 7;
        Check(!c.ActivityFresh && CielAudienceCardState.From(null,c.Activity,true,false,7).phase=="unknown", "stale activity is unknown");
        Check(!CielActivityPresentation.Flow(c.Activity,7).Contains("●"), "stale graph clears highlight");
        ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(!c.ActivityFresh, "duplicate cannot refresh lease");
        live.revision=2;ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.ActivityFresh, "heartbeat restores lease");
        ActivityReceive("{\"v\":1,\"type\":\"activity.state\"}");
        Check(c.Activity==null, "legacy activity rejected");
        ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.Activity==null, "old snapshot cannot hide protocol error");
        live.revision=3;live.v=2;ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.Activity==null,"v2 activity rejected");
        live.v=3;live.continuation.phase="invalid";ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.Activity==null,"invalid continuation rejected");
        live.continuation.phase="waiting";
        live.stream_id="activity-b";live.revision=1;ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        live.stream_id="activity-a";live.revision=99;ActivityReceive(UnityEngine.JsonUtility.ToJson(live));
        Check(c.Activity.stream_id=="activity-b", "retired stream rejected");
        Console.WriteLine($"WORK_DISPLAY_CHECK_OK {checks} checks (production C# with time/JSON/transport stubs)");
    }
}
