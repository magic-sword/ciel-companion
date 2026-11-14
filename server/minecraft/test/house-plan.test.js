import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { runPlan } from '../src/vendor/mindcraft/src/agent/library/plan.js';
import { remaining, materials, clearingTool } from '../src/vendor/mindcraft/src/agent/library/region.js';
import { houseNames, loadHouse, rotate, footprint, houseBlueprint, houseSteps } from '../src/vendor/mindcraft/src/agent/library/house.js';
import { nextLeg } from '../src/vendor/mindcraft/src/agent/library/hunt.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

// Stone up to y = 63 over x, z in -32..31, with surface blocks set by the test.
function fixture(inventory = {}) {
  const world = new World(() => new Chunk()).sync;
  for (let cx = -2; cx <= 1; cx++) for (let cz = -2; cz <= 1; cz++) world.setColumn(cx, cz, new Chunk());
  const set = (x, y, z, name) => world.setBlockStateId(new Vec3(x, y, z), registry.blocksByName[name].defaultState);
  for (let x = -32; x < 32; x++) for (let z = -32; z < 32; z++) for (let y = 60; y < 64; y++) set(x, y, z, 'stone');
  const items = { ...inventory };
  const bot = {
    registry, output: '', interrupt_code: false,
    entity: { position: new Vec3(0.5, 64, 0.5) },
    inventory: { get slots() { return Object.entries(items).filter(([, n]) => n > 0).map(([name, count]) => ({ name, count })); } },
    blockAt: p => world.getBlock(p),
    // The nearest blocks first, as mineflayer returns them.
    findBlocks: ({ matching, maxDistance, count }) => {
      const found = [];
      for (let x = -32; x < 32; x++) for (let z = -32; z < 32; z++) for (let y = 60; y < 70; y++) {
        const p = new Vec3(x, y, z);
        if (p.distanceTo(bot.entity.position) <= maxDistance && matching(world.getBlock(p))) found.push(p);
      }
      return found.sort((a, b) => a.distanceTo(bot.entity.position) - b.distanceTo(bot.entity.position)).slice(0, count);
    },
    pathfinder: { stop() {} }, stopDigging() {}, emit() {},
  };
  return { bot, set, items };
}

test('the upstream house plans load and turn a quarter at a time', () => {
  assert.ok(houseNames().includes('dirt_shelter'));
  const house = loadHouse('dirt_shelter');
  assert.deepEqual(footprint(house), [5, 6]);
  assert.deepEqual(footprint(house, 1), [6, 5]);
  assert.deepEqual(rotate(house.blocks[1], 4), house.blocks[1]);
  assert.equal(rotate([['a', 'b'], ['c', 'd']], 1)[0].join(''), 'ca');
  assert.equal(loadHouse('../package'), null);
});

test('a dirt shelter on a grass patch over stone needs a pickaxe, dirt, a chest, a door, a torch and a bed', () => {
  const { bot, set } = fixture({ oak_log: 2 });
  for (let x = 4; x < 9; x++) for (let z = 4; z < 10; z++) set(x, 63, z, 'grass_block');
  const house = loadHouse('dirt_shelter');
  const blueprint = houseBlueprint(bot, house, new Vec3(4, 63, 4));
  assert.deepEqual(blueprint.levels.map(l => l.coordinates[1]), [62, 63, 64, 65]);
  const need = materials(blueprint, bot);
  assert.deepEqual(Object.keys(need).sort(), ['chest', 'dirt', 'oak_door', 'torch', 'white_bed']);
  assert.equal(need.white_bed, 1);
  assert.equal(need.oak_door, 1);
  // The grass of the patch counts as the plan's dirt; the floor dug into stone does not.
  const cells = remaining(blueprint, bot);
  assert.ok(!cells.some(c => c.coordinates[1] === 63 && c.expected === 'dirt'));
  assert.ok(cells.some(c => c.coordinates[1] === 62 && c.expected === 'dirt' && c.actual === 'stone'));
  assert.equal(clearingTool(blueprint, bot), 'wooden_pickaxe');
  assert.deepEqual(houseSteps(blueprint, bot).map(s => s.id), ['pickaxe', 'chest', 'dirt', 'oak_door', 'torch', 'white_bed', 'house']);
  // A wall torch is the plan's torch.
  const torch = cells.find(c => c.expected === 'torch');
  set(...torch.coordinates, 'wall_torch');
  assert.ok(!remaining(blueprint, bot).some(c => c.expected === 'torch'));
});

test('a step that stops at a choice pauses the plan, and choosing carries the rest of it on', async () => {
  const { bot } = fixture();
  const state = { log: [] };
  const step = (id, needs, run) => ({ id, needs, label: id, done: () => Boolean(state[id]), run, seconds: () => 1 });
  const steps = [
    step('wool', [], async () => {
      bot.pendingChoice = { question: 'how', options: { 'kill:sheep': async () => { state.log.push('kill'); state.wool = true; } } };
    }),
    step('bed', ['wool'], async () => { state.log.push('bed'); state.bed = true; }),
  ];
  assert.equal(await runPlan(bot, steps), false);
  assert.match(bot.output, /The plan waits for that choice; choosing carries it on: wool, bed\./);
  const go = bot.pendingChoice.options['kill:sheep'];
  bot.pendingChoice = null;
  assert.equal(await go(), true);
  assert.deepEqual(state.log, ['kill', 'bed']);
});

test('looking for sheep walks to grass in sight and outward, and along open land when there is none', () => {
  const { bot, set } = fixture();
  for (let x = 12; x < 32; x++) for (let z = -2; z <= 1; z++) set(x, 63, z, 'grass_block');
  const start = bot.entity.position.floored();
  const leg = nextLeg(bot, 'grass_block', [start]);
  assert.deepEqual([leg.heading, leg.ground, leg.target.y], ['east', true, 64]);
  assert.ok(leg.target.x >= 16, 'not a spot next to where the search began');
  // Grass already looked at is passed over; with none left, the open land that reaches farthest.
  for (let z = -32; z < 32; z++) for (let y = 64; y < 68; y++) set(-6, y, z, 'bedrock');
  const again = nextLeg(bot, 'grass_block', [start, new Vec3(22, 64, 0)]);
  assert.equal(again.ground, false);
  assert.notEqual(again.heading, 'west', 'the wall cuts the west off within 8 blocks');
  assert.ok(again.target.distanceTo(start) >= 16);
});
