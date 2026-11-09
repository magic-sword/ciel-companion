// 物を作る手順を決める（体の技 craft と、知識の窓口の facts が使う）。docs/games/minecraft/minecraft-design-ja.md の 21 章。

const total = (g) => Object.values(g).reduce((a, b) => a + b, 0);

// 自分で作ってよい途中の物（足りなければ、持っている物から先に作る）。ほかの材料（原木・丸石・鉄など）は集める物として返す
const PARTS = /_planks$|^stick$|^crafting_table$/;
const PLAN_DEPTH = 4;

// 物を作る手順を決める（持ち物 inv を仮に使いながら）。返すのは { steps: [{name, recipe, times}], missing: {名前: 数}, needsTable, cannot }。
// recipes(id) はその物の作り方の一覧（mineflayer の recipesAll）。作り方が何通りもあるとき（板の種類など）は、
// 持っている物でいちばん足りる作り方を選び、同じならオークを選ぶ（持っていない桜の板を「足りない」と言った。2026-11-07）
export function planCraft(registry, recipes, name, count, inv, hasTable) {
  const have = { ...inv };
  const plan = { steps: [], missing: {}, needsTable: false, cannot: false };
  const ctx = { table: hasTable };
  const nameOf = (id) => registry.items[id]?.name;
  const lack = (n, k) => { plan.missing[n] = (plan.missing[n] ?? 0) + k; };

  // その作り方で、まだ足りない数（途中の物は、持っている材料から作れる分を引く）
  const shortOf = (r, times) => {
    let short = 0;
    for (const d of r.delta ?? []) {
      if (d.count >= 0) continue;
      const n = nameOf(d.id);
      let k = -d.count * times - (have[n] ?? 0);
      if (k > 0 && /_planks$/.test(n)) k -= 4 * (have[n.replace(/_planks$/, '_log')] ?? have[n.replace(/_planks$/, '_stem')] ?? 0);
      if (k > 0) short += k;
    }
    return short;
  };
  // 同じくらい足りるなら、ふつうの材料（オーク・丸石）を選ぶ。深層岩・ブラックストーンは後
  const rank = (n) => (/^oak_|^cobblestone$/.test(n) ? 0 : /deepslate|blackstone/.test(n) ? 2 : 1);
  const prefer = (r) => {
    const ranks = (r.delta ?? []).filter((d) => d.count < 0).map((d) => rank(nameOf(d.id) ?? ''));
    return ranks.includes(2) ? 2 : ranks.includes(0) ? 0 : 1;
  };

  const ensure = (n, k, depth, top) => {
    // 作りたい物そのものは、持っていても「もう k 個」作る（途中の物だけ、持っている分を使う）。
    // 石のつるはしを 1 本持っていて「もう一本」を頼まれ、作る段だけの計画になって、丸石が足りずに止まった（2026-11-07）
    const owned = top ? 0 : (have[n] ?? 0);
    if (owned >= k) {
      have[n] = owned - k;
      return;
    }
    have[n] = 0;
    const short = k - owned;
    const id = registry.itemsByName[n]?.id;
    const list = id === undefined ? [] : recipes(id);
    if (!list.length) {
      if (top) plan.cannot = true;
      else lack(n, short);
      return;
    }
    if (!top && (!PARTS.test(n) || depth > PLAN_DEPTH)) {
      lack(n, short);
      return;
    }
    const r = [...list].sort((x, y) => {
      const tx = Math.ceil(short / (x.result?.count ?? 1)), ty = Math.ceil(short / (y.result?.count ?? 1));
      return shortOf(x, tx) - shortOf(y, ty) || prefer(x) - prefer(y);
    })[0];
    const per = r.result?.count ?? 1;
    const times = Math.ceil(short / per);
    for (const d of r.delta ?? []) {
      if (d.count >= 0) continue;
      ensure(nameOf(d.id), -d.count * times, depth + 1, false);
    }
    if (r.requiresTable && !ctx.table) {
      ctx.table = true;   // 作業台を作って置く（置くと持ち物から減る）
      const missingBefore = total(plan.missing);
      ensure('crafting_table', 1, depth + 1, false);
      if (total(plan.missing) > missingBefore) plan.needsTable = true;
    }
    plan.steps.push({ name: n, recipe: r, times });
    have[n] = (have[n] ?? 0) + times * per - short;
  };

  ensure(name, count, 0, true);
  if (Object.keys(plan.missing).length === 0) plan.needsTable = false;
  return plan;
}
