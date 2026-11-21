import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';

import { blocksFor } from '../src/names.js';
import { canSee, known, knows, notices, remember, rememberAround } from '../src/sight.js';
import { commandBot } from '../src/body-command.js';
import { planCraft } from '../src/craft-plan.js';
import { nearbyBlocks } from '../src/state.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

test('作業台の記憶を別の身体操作と共有し、再参加した身体へは持ち越さない',()=>{
  const {bot,set}=world(),at=new Vec3(4,64,4);
  set(4,64,4,'crafting_table');
  const command=()=>({token:{cancelled:false},operations:new Set()});
  const first=commandBot(bot,command(),{}),second=commandBot(bot,command(),{});
  remember(first,at,'crafting_table');
  bot.entity.position=new Vec3(0,58,0);
  assert.equal(canSee(second,at),false);
  assert.equal(known(second,at),true);assert.equal(known(bot,at),true);
  bot.entity={...bot.entity};
  assert.equal(known(commandBot(bot,command(),{}),at),false);
});

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
