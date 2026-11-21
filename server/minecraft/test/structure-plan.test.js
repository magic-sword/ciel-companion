import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { parseStructure, structureSteps } from '../src/vendor/mindcraft/src/agent/library/structure.js';
import { remaining, materials } from '../src/vendor/mindcraft/src/agent/library/region.js';
import { parseCommandMessage } from '../src/vendor/mindcraft/src/agent/commands/index.js';
import { useVersion } from '../src/vendor/mindcraft/src/utils/mcdata.js';

useVersion('1.21.11');

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);

function fixture(inventory = {}) {
  const world = new World(() => new Chunk()).sync;
  for (let cx = -1; cx <= 0; cx++) for (let cz = -1; cz <= 0; cz++) world.setColumn(cx, cz, new Chunk());
  const set = (x, y, z, name) => world.setBlockStateId(new Vec3(x, y, z), registry.blocksByName[name].defaultState);
  for (let x = -16; x < 16; x++) for (let z = -16; z < 16; z++) set(x, 63, z, 'grass_block');
  const items = { ...inventory };
  const bot = {
    registry, output: '',
    entity: { position: new Vec3(0.5, 64, 0.5) },
    inventory: { get slots() { return Object.entries(items).filter(([, n]) => n > 0).map(([name, count]) => ({ name, count })); } },
    blockAt: p => world.getBlock(p),
  };
  return { bot, set, items };
}

test('a structure is read from a legend and layers, bottom first, rows along z and symbols along x', () => {
  const read = parseStructure(registry, 2, 64, 3, 'c=cobblestone, g=glass', 'ccc,c_c,ccc/cgc,c.c');
  assert.equal(read.error, undefined);
  assert.equal(read.cells, 14);
  const [bottom, top] = read.blueprint.levels;
  assert.deepEqual(bottom.coordinates, [2, 64, 3]);
  assert.deepEqual(top.coordinates, [2, 65, 3]);
  assert.deepEqual(bottom.placement[1], ['cobblestone', 'air', 'cobblestone']);
  // "." leaves a cell as it is, and a short layer is filled with such cells.
  assert.deepEqual(top.placement[1], ['cobblestone', '', 'cobblestone']);
  assert.deepEqual(top.placement[2], ['', '', '']);
});

test('a structure that cannot be read says why', () => {
  const error = (legend, layers) => parseStructure(registry, 0, 64, 0, legend, layers).error;
  assert.match(error('c=cobblestone', 'cx'), /"x" is not in the legend/);
  assert.match(error('c=stone_brick', 'c'), /stone_brick is not a block name/);
  assert.match(error('c cobblestone', 'c'), /symbol=block_name/);
  assert.match(error('.=dirt', '.'), /kept for a cell left as it is/);
  assert.match(error('c=dirt', '...'), /asks for no blocks/);
  assert.match(error('c=dirt', 'c'.repeat(17)), /at most 16 blocks on each side/);
});

test('the structure plan gets its materials before building, and reads the cells left from the world', () => {
  const { bot, set, items } = fixture({ cobblestone: 2 });
  const { blueprint } = parseStructure(registry, 2, 64, 2, 'c=cobblestone', 'ccc');
  assert.deepEqual(materials(blueprint, bot), { cobblestone: 3 });
  const steps = Object.fromEntries(structureSteps(blueprint, bot).map(s => [s.id, s]));
  assert.deepEqual(steps.structure.needs, ['pickaxe', 'cobblestone']);
  assert.equal(steps.pickaxe.done(bot), true);
  assert.equal(steps.cobblestone.done(bot), false);
  items.cobblestone = 3;
  assert.equal(steps.cobblestone.done(bot), true);
  set(2, 64, 2, 'cobblestone');
  assert.equal(remaining(blueprint, bot).length, 2);
  // A pickaxe is wanted when stone stands where the plan clears a cell.
  const clearing = parseStructure(registry, 5, 64, 5, 'c=cobblestone', 'c_').blueprint;
  set(6, 64, 5, 'stone');
  assert.equal(structureSteps(clearing, bot)[0].done(bot), false);
});

test('the commands that act on a place read their coordinates, and a plan with commas and slashes stays one argument', () => {
  const built = parseCommandMessage('!buildStructure(10, 64, -5, "c=cobblestone, g=glass", "ccc,c_c,ccc/cgc,c_c,ccc")');
  assert.equal(typeof built, 'object', built);
  assert.deepEqual(built.args, [10, 64, -5, 'c=cobblestone, g=glass', 'ccc,c_c,ccc/cgc,c_c,ccc']);
  assert.deepEqual(parseCommandMessage('!placeBlockAt("torch", 1, 65, -2)').args, ['torch', 1, 65, -2]);
  assert.deepEqual(parseCommandMessage('!breakBlockAt(1, 64, -2)').args, [1, 64, -2]);
  assert.deepEqual(parseCommandMessage('!useBlockAt(3, 64, 0)').args, [3, 64, 0]);
  assert.deepEqual(parseCommandMessage('!wait(30)').args, [30]);
});
