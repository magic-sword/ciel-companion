// ゲーム内部のレシピ計画。会話ホストは段を進めず、work契約で依頼する。docs/game-work-contract-ja.md。
// - 作り方は craft-plan.js（体の技 craft と、知識の窓口の facts と同じ部品）。持ち物と、近くに作業台があるかを見て決める。
// - 足りない材料は「集める」段にする。素手（今の道具）で取れない材料なら、先にその道具を「作る」段を足す。
// - 集める元のブロックが無い材料（小麦・糸など）は「心に任せる」段にする（どうやって手に入れるかは心が考える）。
// - 作る段は、作りたい物だけ（板・棒・作業台は、体の技 craft が途中で作る）。
import { planCraft } from './craft-plan.js';
import { blocksFor } from './names.js';

const TOOL_TIERS = ['wooden', 'golden', 'stone', 'copper', 'iron', 'diamond', 'netherite'];
const DEPTH = 3;   // 道具の道具（石のツルハシのための木のツルハシ）まで

// inv：{名前: 数}。hasTable：近くに作業台があるか。recipes(id)：作り方の一覧
export function planGoal(registry, recipes, item, count, inv, hasTable) {
  const have = { ...inv };
  const steps = [];
  let table = hasTable || (have.crafting_table ?? 0) > 0;

  const canHarvest = (block) => {
    if (!block.harvestTools) return true;
    return Object.keys(block.harvestTools).some((id) => (have[registry.items[Number(id)]?.name] ?? 0) > 0);
  };
  const weakest = (blocks) => {
    const tools = blocks.flatMap((b) => Object.keys(b.harvestTools ?? {}).map((id) => registry.items[Number(id)]?.name)).filter(Boolean);
    const tier = (n) => TOOL_TIERS.findIndex((t) => n.startsWith(t + '_'));
    return tools.sort((a, b) => tier(a) - tier(b))[0] ?? null;
  };

  const make = (name, n, depth) => {
    // 足りない材料を 1 つ集めるたびに数え直す（材料を集めるために作った道具の余り（棒など）を、次の材料に使う）
    for (let i = 0; i < 12; i++) {
      const plan = planCraft(registry, recipes, name, n, have, table);
      if (plan.cannot) {   // 作り方の無い物：集めるか、心に任せる
        gather(name, n, depth);
        return;
      }
      const miss = Object.entries(plan.missing);
      if (!miss.length) break;
      const [raw, k] = miss[0];
      gather(raw, k, depth);
      if (steps.at(-1)?.kind === 'mind') have[raw] = (have[raw] ?? 0) + k;   // 心が手に入れたことにして先へ
    }
    steps.push({ kind: 'craft', item: name, count: n });
    // 作ったつもりで持ち物を進める（材料は使った分を引く。ざっとでよい。体が作るときに確かめる）
    const after = planCraft(registry, recipes, name, n, have, table);
    if (!Object.keys(after.missing).length) {
      for (const s of after.steps) {
        for (const d of s.recipe.delta ?? []) {
          const nm = registry.items[d.id]?.name;
          if (nm) have[nm] = Math.max(0, (have[nm] ?? 0) + d.count * s.times);
        }
      }
      if (after.steps.some((s) => s.name === 'crafting_table')) table = true;
    }
    have[name] = (have[name] ?? 0);
  };

  const gather = (name, n, depth) => {
    const blocks = blocksFor(registry, name);
    if (!blocks.length) {
      steps.push({ kind: 'mind', item: name, count: n });
      return;
    }
    if (!blocks.some(canHarvest)) {
      const tool = weakest(blocks);
      if (tool && depth < DEPTH) make(tool, 1, depth + 1);
      if (tool) have[tool] = Math.max(1, have[tool] ?? 0);
    }
    steps.push({ kind: 'gather', item: name, count: n });
    have[name] = (have[name] ?? 0) + n;
  };

  if (!registry.itemsByName[item]) return { error: 'unknown_item' };
  make(item, count, 0);
  return { steps };
}
