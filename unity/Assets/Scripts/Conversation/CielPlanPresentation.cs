// 計画グラフ（plan v1）の見せ方。ゲームが報告した節だけを並べ、段や進み具合を作り足さない。
// 見積もりは完了予測ではなく、ゲームが節ごとに見込んだ時間。
using System;
using System.Collections.Generic;

namespace Ciel.Conversation
{
    public sealed class CielPlanPresentation
    {
        public sealed class Child
        {
            public string text = "", state = "", stateLabel = "", chosen = "";
            public string[] options = Array.Empty<string>();
        }

        public sealed class Node
        {
            public string id = "", text = "", state = "", stateLabel = "", estimate = "", chosen = "";
            public int column, row;
            public bool current;
            public string[] needs = Array.Empty<string>(), options = Array.Empty<string>();
            public readonly List<Child> children = new List<Child>();
            public int hiddenDone;   // 子の完了で畳んだ数
        }

        public bool visible, stale, finished;
        public string title = "", summary = "", note = "", key = "";
        public readonly List<Node> nodes = new List<Node>();
        public int columns;

        // 動作の種類（ゲームに依存しない語彙）と状態の言葉
        public static readonly Dictionary<string, string> Verbs = new Dictionary<string, string> {
            ["obtain"] = "入手", ["make"] = "製作", ["build"] = "建てる", ["find"] = "探す",
            ["wait"] = "待つ", ["decide"] = "選ぶ", ["do"] = "実行" };
        public static readonly Dictionary<string, string> States = new Dictionary<string, string> {
            ["pending"] = "これから", ["ready"] = "着手できる", ["running"] = "実行中", ["done"] = "完了",
            ["failed"] = "できなかった", ["waiting_choice"] = "選択待ち" };
        const int ShownChildren = 6;

        static string Text(CielConversation.PlanNode n) =>
            (Verbs.TryGetValue(n.kind ?? "", out var verb) ? verb : "実行") + "　" + (n.label ?? "");

        static string[] Options(CielConversation.PlanChoice c)
        {
            if (c?.options == null) return Array.Empty<string>();
            var list = new List<string>();
            foreach (var o in c.options) if (!string.IsNullOrEmpty(o?.id)) list.Add(o.id);
            return list.ToArray();
        }

        public static CielPlanPresentation From(CielConversation.GoalState g)
        {
            var p = new CielPlanPresentation();
            var plan = g?.task?.plan;
            if (g == null || !g.HasGoal || plan == null || !plan.Valid) return p;
            p.visible = true;
            p.finished = plan.finished;
            p.stale = !g.Fresh;
            p.key = $"{plan.plan_id}:{plan.revision}:{p.stale}";
            p.title = string.IsNullOrEmpty(plan.title) ? g.task.title : plan.title;
            p.note = p.stale ? "最新の状態を確認できていません" : plan.finished ? "計画は終わりました" : "見積もりは完了予測ではありません";

            var top = new List<CielConversation.PlanNode>();
            var byId = new Dictionary<string, CielConversation.PlanNode>();
            foreach (var n in plan.nodes)
            {
                if (n == null || string.IsNullOrEmpty(n.id) || byId.ContainsKey(n.id)) continue;
                byId[n.id] = n;
            }
            foreach (var n in byId.Values) if (string.IsNullOrEmpty(n.parent) || !byId.ContainsKey(n.parent)) top.Add(n);
            // 子は最上位の節の下へ（入れ子は一段にまとめる）
            string Root(CielConversation.PlanNode n)
            {
                var seen = new HashSet<string>();
                while (!string.IsNullOrEmpty(n.parent) && byId.TryGetValue(n.parent, out var up) && seen.Add(n.id)) n = up;
                return n.id;
            }
            // 列は依存の深さ（いちばん長い前提の鎖）
            var depth = new Dictionary<string, int>();
            int Depth(CielConversation.PlanNode n, int guard)
            {
                if (depth.TryGetValue(n.id, out var d)) return d;
                d = 0;
                if (guard < 64 && n.needs != null)
                    foreach (var need in n.needs)
                        if (byId.TryGetValue(need, out var m) && string.IsNullOrEmpty(m.parent)) d = Math.Max(d, Depth(m, guard + 1) + 1);
                return depth[n.id] = d;
            }
            var current = new HashSet<string>(plan.current ?? Array.Empty<string>());
            var views = new Dictionary<string, Node>();
            var rows = new Dictionary<int, int>();
            foreach (var n in top)
            {
                var column = Depth(n, 0);
                rows.TryGetValue(column, out var row);
                rows[column] = row + 1;
                var view = new Node {
                    id = n.id, text = Text(n), state = n.state ?? "", column = column, row = row,
                    stateLabel = States.TryGetValue(n.state ?? "", out var s) ? s : "",
                    estimate = n.estimate_s >= 0 && n.state != "done" ? $"見積もり約{n.estimate_s}秒" : "",
                    needs = n.needs ?? Array.Empty<string>(), options = Options(n.choice),
                    chosen = n.choice?.chosen ?? "" };
                p.columns = Math.Max(p.columns, column + 1);
                views[n.id] = view;
                p.nodes.Add(view);
            }
            foreach (var n in byId.Values)
            {
                if (views.ContainsKey(n.id)) continue;
                var owner = views[Root(n)];
                owner.children.Add(new Child { text = Text(n), state = n.state ?? "",
                    stateLabel = States.TryGetValue(n.state ?? "", out var s) ? s : "",
                    options = Options(n.choice), chosen = n.choice?.chosen ?? "" });
            }
            foreach (var view in p.nodes)
            {
                view.current = current.Contains(view.id) || view.children.Exists(c => c.state == "running" || c.state == "waiting_choice");
                // 長い子の並びは、終わったものから畳む
                while (view.children.Count > ShownChildren)
                {
                    var i = view.children.FindIndex(c => c.state == "done");
                    if (i < 0) break;
                    view.children.RemoveAt(i);
                    view.hiddenDone++;
                }
                if (view.children.Count > ShownChildren) view.children.RemoveRange(ShownChildren, view.children.Count - ShownChildren);
            }
            p.nodes.Sort((a, b) => a.column != b.column ? a.column.CompareTo(b.column) : a.row.CompareTo(b.row));
            p.summary = NowLine(plan);
            return p;
        }

        /// 状態カードに載せる一行：いまの節（選択待ちならその選択）と、終わった節の数
        public static string NowLine(CielConversation.PlanInfo plan)
        {
            if (plan == null || !plan.Valid) return "";
            CielConversation.PlanNode now = null, waiting = null;
            int done = 0, total = 0;
            foreach (var n in plan.nodes)
            {
                if (n == null) continue;
                if (string.IsNullOrEmpty(n.parent))
                {
                    total++;
                    if (n.state == "done") done++;
                }
                if (n.state == "waiting_choice" && n.kind == "decide") waiting = n;
                else if (n.state == "running") now = n;   // 最後の（いちばん内側の）実行中の節
            }
            var count = total > 0 ? $"（完了 {done}/{total}）" : "";
            if (waiting != null)
            {
                var options = Options(waiting.choice);
                return $"選択待ち：{waiting.label}" + (options.Length > 0 ? "（" + string.Join(" / ", options) + "）" : "") + count;
            }
            return now != null ? Text(now) + count : (plan.finished ? "計画は終わりました" + count : "");
        }
    }
}
