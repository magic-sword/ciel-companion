import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';

import { blocksFor } from '../src/names.js';
import { canSee, known, knows, notices, rememberAround } from '../src/sight.js';
import { harvestable, weakestTool } from '../src/skills.js';
import { planCraft } from '../src/craft-plan.js';
import { nearbyBlocks } from '../src/state.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

// 地面（y 63 まで石、上に草）。シエルは (0, 64, 0) に立つ
function world() {
  const w = new World(() => new Chunk()).sync;
  for (const cx of [-1, 0]) for (const cz of [-1, 0]) w.setColumn(cx, cz, new Chunk());
  const set = (x, y, z, name) => w.setBlockStateId(new Vec3(x, y, z), registry.blocksByName[name].defaultState);
  for (let x = -8; x <= 8; x++) {
    for (let z = -8; z <= 8; z++) {
      for (let y = 50; y <= 62; y++) set(x, y, z, 'stone');
      set(x, 63, z, 'grass_block');
    }
  }
  const bot = {
    registry,
    world: w,
    entity: { position: new Vec3(0.5, 64, 0.5), eyeHeight: 1.62 },
    blockAt: (p) => w.getBlock(p),
    inventory: { items: () => [] },
    findBlocks: ({ matching }) => {
      const ids = new Set([matching].flat());
      const found = [];
      for (let x = -8; x <= 8; x++) for (let y = 50; y <= 70; y++) for (let z = -8; z <= 8; z++) {
        const p = new Vec3(x, y, z);
        if (ids.has(w.getBlock(p)?.type)) found.push(p);
      }
      return found;
    },
  };
  return { bot, set };
}

test('埋まった鉱石は見えない。地面の花・むき出しの鉱石は見える', () => {
  const { bot, set } = world();
  set(2, 58, 0, 'coal_ore');          // 地中
  set(3, 64, 0, 'dandelion');         // 地面の花（当たりの形が無い）
  set(-3, 63, 0, 'iron_ore');         // 地面に出ている
  set(0, 64, 4, 'stone');             // 壁の向こうに花
  set(0, 65, 4, 'stone');
  set(0, 64, 6, 'poppy');
  set(-1, 64, 5, 'stone'); set(1, 64, 5, 'stone'); set(-1, 65, 5, 'stone'); set(1, 65, 5, 'stone');
  set(0, 64, 5, 'stone'); set(0, 65, 5, 'stone'); set(0, 66, 5, 'stone'); set(0, 66, 6, 'stone'); set(0, 64, 7, 'stone'); set(0, 65, 7, 'stone'); set(0, 65, 6, 'stone');
  set(-1, 64, 6, 'stone'); set(1, 64, 6, 'stone'); set(-1, 65, 6, 'stone'); set(1, 65, 6, 'stone');
  assert.equal(canSee(bot, new Vec3(2, 58, 0)), false);
  assert.equal(canSee(bot, new Vec3(3, 64, 0)), true);
  assert.equal(canSee(bot, new Vec3(-3, 63, 0)), true);
  assert.equal(canSee(bot, new Vec3(0, 64, 6)), false);
  const counts = nearbyBlocks(bot);
  assert.equal(counts.coal_ore, undefined);
  assert.equal(counts.poppy, undefined);
  assert.equal(counts.dandelion, 1);
  assert.equal(counts.iron_ore, 1);
});

test('見たブロックは覚えていて、掘った木の幹の上も知っている', () => {
  const { bot, set } = world();
  for (let y = 64; y <= 68; y++) set(4, y, 4, 'oak_log');
  assert.equal(knows(bot, new Vec3(4, 64, 4)), true);
  bot.entity.position = new Vec3(-6.5, 64, -6.5);
  assert.equal(known(bot, new Vec3(4, 64, 4)), true);   // 離れても覚えている
  set(4, 64, 4, 'air');                                  // 掘った
  assert.equal(known(bot, new Vec3(4, 64, 4)), false);
  rememberAround(bot, new Vec3(4, 64, 4), (n) => n === 'oak_log');
  assert.equal(known(bot, new Vec3(4, 65, 4)), true);
});

test('敵は見えるか、近ければ気づく', () => {
  const { bot, set } = world();
  for (let y = 64; y <= 66; y++) for (let x = -2; x <= 2; x++) set(x, y, 3, 'stone');
  assert.equal(notices(bot, { position: new Vec3(0.5, 64, 8.5), height: 1.95 }), false);   // 壁の向こう
  assert.equal(notices(bot, { position: new Vec3(7.5, 64, 0.5), height: 1.95 }), true);    // 見える
  assert.equal(notices(bot, { position: new Vec3(0.5, 60, 0.5), height: 1.95 }), true);    // 足の下でも近い
  assert.equal(notices(bot, { position: new Vec3(2.5, 52, 2.5), height: 1.95 }), false);   // 深い洞窟
});

test('呼び名から集めるブロック', () => {
  const names = (n) => blocksFor(registry, n).map((b) => b.name);
  assert.ok(names('flower').includes('dandelion') && names('flower').includes('poppy'));
  assert.deepEqual(names('dirt').slice(0, 2), ['dirt', 'grass_block']);
  assert.deepEqual(names('coal'), ['coal_ore', 'deepslate_coal_ore']);
  assert.deepEqual(names('raw_iron'), ['iron_ore', 'deepslate_iron_ore']);
  assert.ok(names('log').includes('oak_log') && !names('log').includes('stripped_oak_log'));
  assert.deepEqual(names('oak_logs'), ['oak_log']);
  assert.deepEqual(names('poppies'), ['poppy']);
  assert.deepEqual(names('flowerz'), []);
});

test('掘る道具と、作る材料', () => {
  const bot = { registry, inventory: { items: () => [] } };
  assert.equal(harvestable(bot, registry.blocksByName.dandelion), true);
  assert.equal(harvestable(bot, registry.blocksByName.stone), false);
  assert.equal(weakestTool(bot, [registry.blocksByName.iron_ore]), 'stone_pickaxe');
  assert.equal(weakestTool(bot, [registry.blocksByName.stone]), 'wooden_pickaxe');
  const pick = registry.itemsByName.wooden_pickaxe.id;
  bot.inventory.items = () => [{ name: 'wooden_pickaxe', type: pick, count: 1 }];
  assert.equal(harvestable(bot, registry.blocksByName.stone), true);

});

test('ふだんの歩き方：自然のブロックだけ壊し、手持ちの土・丸石を積み、4 段まで飛び降りる', async () => {
  const { playerMovements, escapeMovements } = await import('../src/movements.js');
  const bot = { registry, version: '1.21.11', world: {}, inventory: { items: () => [] } };
  const m = playerMovements(bot);
  assert.equal(m.canDig, true);
  assert.equal(m.allow1by1towers, true);
  assert.equal(m.maxDropDown, 4);
  assert.equal(m.liquidCost, 10);   // 水の中はなるべく通らない
  assert.ok(m.scafoldingBlocks.includes(registry.itemsByName.dirt.id));
  assert.ok(!m.scafoldingBlocks.includes(registry.itemsByName.oak_planks.id));
  assert.ok(m.blocksCantBreak.has(registry.blocksByName.oak_planks.id));     // 建物に使うものは壊さない
  assert.ok(!m.blocksCantBreak.has(registry.blocksByName.oak_leaves.id));
  assert.ok(!m.blocksCantBreak.has(registry.blocksByName.dirt.id));
  assert.equal(escapeMovements(bot).maxDropDown, 12);   // 体力 20：12 段まで（ダメージ 9、体力 11 残る）
  const { escapeDrop } = await import('../src/movements.js');
  assert.equal(escapeDrop(14), 9);
  assert.equal(escapeDrop(6), 4);   // 体力が少なければ、ふだんの高さまで
});

test('見張り：動かず・掘らず・置かずのままなら、行き先を取り消して Stuck で終える', async () => {
  const { watched } = await import('../src/skills.js');
  const { EventEmitter } = await import('node:events');
  const bot = new EventEmitter();
  bot.entity = { position: new Vec3(0, 64, 0) };
  let goal = 'log';
  bot.pathfinder = { isMining: () => false, isBuilding: () => false, setGoal: (g) => { goal = g; bot.emit('goal_updated', g); } };
  // 行き先が変わるまで終わらない goto（止まったままの経路探索）
  const goto = () => new Promise((_, reject) => bot.once('goal_updated', () => reject(Object.assign(new Error('changed'), { name: 'GoalChanged' }))));
  await assert.rejects(watched(bot, goto, 1500), { name: 'Stuck' });
  assert.equal(goal, null);
  // 動いていれば取り消さない
  const moving = setInterval(() => { bot.entity.position = bot.entity.position.offset(1, 0, 0); }, 300);
  assert.equal(await watched(bot, () => new Promise((r) => setTimeout(() => r('ok'), 2500)), 1500), 'ok');
  clearInterval(moving);
});

test('掘る前に、足が地面に着くのを待つ', async () => {
  const { groundedDig } = await import('../src/skills.js');
  let ticks = 0;
  const started = [];
  const bot = {
    entity: { onGround: false, isInWater: false },
    dig: async (b) => { started.push({ block: b.name, onGround: bot.entity.onGround }); },
    waitForTicks: async () => { ticks += 1; if (ticks === 3) bot.entity.onGround = true; },
    digTime: () => (bot.entity.onGround ? 3000 : 15000),
    heldItem: null,
  };
  const logs = [];
  groundedDig(bot, (m) => logs.push(m));
  await bot.dig({ name: 'oak_log' });
  assert.deepEqual(started, [{ block: 'oak_log', onGround: true }]);
  assert.equal(logs.length, 0);
  // 水の中では待たない（待っても速くならない）。時間のかかる掘り方はログに残す
  bot.entity.onGround = false;
  bot.entity.isInWater = true;
  await bot.dig({ name: 'oak_log' });
  assert.equal(started[1].onGround, false);
  assert.match(logs[0], /掘るのに時間がかかる block=oak_log ms=15000/);
});

test('掘ったあと、まわりに落ちた物を拾いに行く（真ん中から離れて落ちた物も）', async () => {
  const { pickUpNear } = await import('../src/skills.js');
  const { EventEmitter } = await import('node:events');
  const bot = new EventEmitter();
  bot.entity = { position: new Vec3(0, 64, 0) };
  bot.entities = {
    7: { id: 7, name: 'item', position: new Vec3(3.2, 64, 1.1) },    // 原木から 2 ブロックずれて落ちた
    8: { id: 8, name: 'item', position: new Vec3(30, 64, 30) },      // 遠くの物は拾いに行かない
  };
  const went = [];
  bot.waitForTicks = async () => {};
  bot.pathfinder = {
    setMovements: () => {},
    goto: async (goal) => { went.push([goal.x, goal.z]); bot.entity.position = new Vec3(goal.x, goal.y, goal.z); delete bot.entities[7]; },
    setGoal: () => {},
  };
  bot.registry = registry;
  bot.inventory = { items: () => [] };
  await pickUpNear(bot, new Vec3(1, 66, 1), null, { cancelled: false });
  assert.equal(went.length, 1);
  assert.ok(bot.entities[8]);
  assert.equal(bot.entities[7], undefined);
});

test('ツルハシを作る手順：原木から板・棒・作業台を先に作り、足りなければ原木の数で返す', () => {
  const { Recipe } = require('prismarine-recipe')(registry);
  const recipes = (id) => Recipe.find(id, null);
  const steps = (p) => p.steps.map((s) => `${s.name}×${s.times}`);
  // 原木 3 本・作業台なし：板 3 回（12 枚）→ 作業台 → 棒 → ツルハシ
  let p = planCraft(registry, recipes, 'wooden_pickaxe', 1, { oak_log: 3 }, false);
  assert.deepEqual(p.missing, {});
  assert.equal(p.steps.at(-1).name, 'wooden_pickaxe');
  assert.ok(steps(p).includes('crafting_table×1'));
  assert.ok(p.steps.every((s) => !/^(cherry|acacia|birch)_/.test(s.name)));
  // 近くに作業台があれば、原木 2 本で足りる
  p = planCraft(registry, recipes, 'wooden_pickaxe', 1, { oak_log: 2 }, true);
  assert.deepEqual(p.missing, {});
  assert.ok(!steps(p).includes('crafting_table×1'));
  // 何も無ければ、オークの原木の数で返す（持っていない桜の板とは言わない）
  p = planCraft(registry, recipes, 'wooden_pickaxe', 1, {}, true);
  assert.deepEqual(p.missing, { oak_log: 2 });
  // 白樺の原木を持っていれば、白樺の板で作る
  p = planCraft(registry, recipes, 'wooden_pickaxe', 1, { birch_log: 2 }, true);
  assert.deepEqual(p.missing, {});
  assert.ok(steps(p).some((s) => s.startsWith('birch_planks')));
  // 石のツルハシ：丸石は作らず、集める物として返す
  p = planCraft(registry, recipes, 'stone_pickaxe', 1, { oak_log: 1 }, true);
  assert.deepEqual(p.missing, { cobblestone: 3 });
  // 作り方の無い物
  assert.equal(planCraft(registry, recipes, 'oak_log', 1, {}, true).cannot, true);
});
