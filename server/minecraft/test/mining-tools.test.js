import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { Runner } from '../src/skills.js';
import { Guard } from '../src/guard.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const { Recipe } = require('prismarine-recipe')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

function fixture(inventory = {}) {
  const inv = { ...inventory }, actions = [], events = [];
  const world = new World(() => new Chunk()).sync;
  for (const x of [-1, 0]) for (const z of [-1, 0]) world.setColumn(x, z, new Chunk());
  const set = (p, name) => world.setBlockStateId(p, registry.blocksByName[name].defaultState);
  const resources = [];
  for (let x = -4; x <= 4; x++) for (let z = -4; z <= 4; z++) {
    for (let y = 60; y <= 63; y++) set(new Vec3(x, y, z), 'stone');
  }
  const bot = {
    registry, world, version: '1.21.11', entities: {},
    entity: { position: new Vec3(0.5, 64, 0.5), onGround: true, yaw: 0 },
    heldItem: null,
    inventory: { items: () => Object.entries(inv).filter(([, n]) => n > 0).map(([name, count]) => ({ name, count, type: registry.itemsByName[name].id })) },
    blockAt: p => world.getBlock(p),
    findBlocks: ({ matching }) => resources.filter(p => [matching].flat().includes(world.getBlock(p).type)),
    canDigBlock: () => true,
    recipesAll: id => Recipe.find(id, null),
    waitForTicks: async () => {},
    equip: async item => { bot.heldItem = item; actions.push(['equip', item.name]); },
    lookAt: async () => {},
    placeBlock: async (below, face) => {
      const p = below.position.plus(face);
      set(p, 'crafting_table');
      resources.push(p);
      inv.crafting_table--;
    },
    craft: async (recipe, times) => {
      for (const d of recipe.delta) {
        const name = registry.items[d.id].name;
        inv[name] = (inv[name] ?? 0) + d.count * times;
        assert.ok(inv[name] >= 0, `insufficient ${name}`);
      }
      actions.push(['craft', registry.items[recipe.result.id].name]);
    },
    pathfinder: { setMovements() {}, setGoal() {}, stop() {}, goto: async () => {} },
    collectBlock: {
      collect: async block => {
        const drop = block.name === 'stone' ? 'cobblestone' : block.name === 'iron_ore' ? 'raw_iron' : block.name;
        assert.ok(!block.harvestTools || Object.keys(block.harvestTools).some(id => bot.inventory.items().some(i => i.type === Number(id))));
        inv[drop] = (inv[drop] ?? 0) + 1;
        set(block.position, 'air');
        actions.push(['collect', drop]);
      },
    },
    dig: async block => {
      if (resources.some(p=>p.equals(block.position))) return bot.collectBlock.collect(block);
      actions.push(['dig', block.name, bot.heldItem?.name]);
      // 最初の探索用採掘を確認したら終了する（地下探索の距離はこの試験の対象外）。
      runner.current.token.cancelled = true;
    },
  };
  bot.tool = { equipForBlock: async block => {
    const item = bot.inventory.items().reverse().find(i => block.harvestTools?.[i.type]);
    if (item) await bot.equip(item, 'hand');
  } };
  const runner = new Runner((type, fields) => { if (type !== 'body') events.push({ type, ...fields }); });
  runner.bot = bot;
  const add = (x, y, z, name) => { const p = new Vec3(x, y, z); set(p, name); resources.push(p); };
  const run = (skill = 'find', args = { block: 'iron', how: 'dig', max: 1 }) => runner.start({ id: 1, skill, args });
  return { bot, runner, inv, actions, events, add, run };
}

test('渡された石のツルハシを装備してから地下を掘る', async () => {
  const f = fixture({ stone_pickaxe: 1 });
  await f.run();
  assert.deepEqual(f.actions, [['equip', 'stone_pickaxe'], ['dig', 'stone', 'stone_pickaxe']]);
});

test('木のツルハシだけなら、鉄の探索前に石のツルハシを作る', async () => {
  const f = fixture({ wooden_pickaxe: 1, cobblestone: 3, stick: 2 });
  f.add(2, 64, 0, 'crafting_table');
  await f.run();
  assert.deepEqual(f.actions, [['craft', 'stone_pickaxe'], ['equip', 'stone_pickaxe'], ['dig', 'stone', 'stone_pickaxe']]);
});

test('道具がなければ原木と石から木・石のツルハシを作って探索する', async () => {
  const f = fixture();
  for (let x = 1; x <= 3; x++) f.add(x, 64, 2, 'oak_log');
  // Exposed wall at foot height: this test isolates tool preparation, not stair movement.
  for (let x = 1; x <= 3; x++) f.add(x, 64, -2, 'stone');
  await f.run();
  assert.equal(f.inv.stone_pickaxe, 1, JSON.stringify({ events: f.events, actions: f.actions, inv: f.inv }));
  assert.ok(f.actions.some(a => a[0] === 'craft' && a[1] === 'wooden_pickaxe'));
  assert.equal(f.actions.filter(a => a[0] === 'collect' && a[1] === 'cobblestone').length, 3);
  assert.deepEqual(f.actions.at(-1), ['dig', 'stone', 'stone_pickaxe']);
});

test('石は足元より横の露出面から集め、帰還で使った分を補充する', async () => {
  const f = fixture({wooden_pickaxe:1});
  f.add(0,63,0,'stone');
  for(let x=1;x<=4;x++)f.add(x,64,-2,'stone');
  const collect=f.bot.collectBlock.collect;
  f.bot.collectBlock.collect=async block=>{
    assert.ok(block.position.y>=Math.floor(f.bot.entity.position.y),'must not mine the floor');
    return collect(block);
  };
  let returns=0;
  f.bot.pathfinder.goto=async ()=>{
    if(returns++===0)f.inv.cobblestone--;
  };
  await f.run('collect',{block:'cobblestone',count:3});
  const done=f.events.at(-1);
  assert.equal(done.ok,true,JSON.stringify(done));
  assert.equal(f.inv.cobblestone,3);
  assert.equal(done.note.gained.cobblestone,3);
  assert.equal(done.note.returned,true);
  assert.equal(f.actions.filter(a=>a[0]==='collect').length,4);
});

test('石を掘る前に足場用の土を確保する',async()=>{
  const f=fixture({wooden_pickaxe:1});
  for(let x=1;x<=4;x++)f.add(x,64,2,'dirt');
  f.add(1,64,-2,'stone');
  await f.run('collect',{block:'cobblestone',count:1});
  assert.equal(f.events.at(-1).ok,true,JSON.stringify(f.events.at(-1)));
  assert.equal(f.inv.dirt,4);
  const collected=f.actions.filter(a=>a[0]==='collect').map(a=>a[1]);
  assert.deepEqual(collected,['dirt','dirt','dirt','dirt','cobblestone']);
});

test('作成ができなければ探索用の石を素手で掘らず失敗を返す', async () => {
  const f = fixture();
  f.bot.recipesAll = () => [];
  await f.run();
  assert.equal(f.events.at(-1).reason, 'missing_materials');
  assert.equal(f.actions.length, 0);
});

test('採集を直接頼んだ場合も、石のツルハシを作ってから鉄を集める', async () => {
  const f = fixture({ wooden_pickaxe: 1, cobblestone: 3, stick: 2 });
  f.add(2, 64, 0, 'crafting_table');
  f.add(2, 64, -2, 'iron_ore');
  await f.run('collect', { block: 'iron', count: 1 });
  assert.equal(f.inv.stone_pickaxe, 1);
  assert.equal(f.inv.raw_iron, 1);
  assert.equal(f.events.at(-1).ok, true);
  assert.deepEqual(f.events.at(-1).note.gained, { raw_iron: 1 });
});

test('装備係が不適切な道具を選んでも採掘可能な道具を手に持つ', async () => {
  const f = fixture({ stone_pickaxe: 1 });
  f.bot.tool.equipForBlock = async () => {};
  await f.run();
  assert.deepEqual(f.actions.at(-1), ['dig', 'stone', 'stone_pickaxe']);
});

test('作成中に停止されたら探索を始めない', async () => {
  const f = fixture({ wooden_pickaxe: 1, cobblestone: 3, stick: 2 });
  f.add(2, 64, 0, 'crafting_table');
  const craft = f.bot.craft;
  f.bot.craft = async (...args) => { await craft(...args); f.runner.current.token.cancelled = true; };
  await f.run();
  assert.deepEqual(f.actions, [['craft', 'stone_pickaxe']]);
  assert.equal(f.events.at(-1).ok, false);
});

test('足元を掘る場合も道具の装備失敗を無視しない', async () => {
  const f = fixture({ stone_pickaxe: 1 });
  f.bot.tool.equipForBlock = async () => { throw new Error('NoPath: equipment failed'); };
  await f.run('dig_down', { depth: 1 });
  assert.equal(f.actions.length, 0);
  assert.equal(f.events.at(-1).ok, false);
});

test('防御待ちの追従から材料不足の工作へ切り替えても、追従と待ち手を残さない', async () => {
  const f = fixture();
  const guard = new Guard(() => {}, 'owner');
  guard.active = true;
  f.runner.guard = guard;
  f.runner.owner = 'owner';
  f.bot.players = { owner: { entity: { id: 1, position: new Vec3(1, 64, 0) } } };
  const following = f.runner.start({ id: 1, skill: 'follow', args: {} });
  const crafting = f.runner.start({ id: 2, skill: 'craft', args: { item: 'wooden_pickaxe', count: 1 } });
  await Promise.all([following, crafting]);
  assert.equal(f.runner.current, null);
  assert.equal(guard._waiters.length, 0);
  assert.equal(f.events.find(e => e.type === 'done' && e.id === 2).reason, 'missing_materials');
  assert.deepEqual(f.actions, []);
});
