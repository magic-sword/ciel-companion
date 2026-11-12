import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionScope } from '../src/mindcraft/action-scope.js';
import { MindcraftRunner } from '../src/mindcraft/runtime.js';
import { protectWorld } from '../src/mindcraft/protection.js';
import { Vec3 } from 'vec3';
import { parseCommand } from '../src/protocol.js';

test('a late equip completion cannot start digging after an interrupt', async () => {
  let release, digs = 0;
  const bot = { equip: () => new Promise(r => { release = r; }), dig: async () => { digs++; } };
  const scope = new ActionScope(bot);
  const run = scope.run(async () => { await bot.equip(); await bot.dig(); });
  scope.interrupt(); release();
  await assert.rejects(run, /interrupted/);
  await scope.settle();
  assert.equal(digs, 0);
  await scope.run(() => bot.dig());
  assert.equal(digs, 1);
});

test('new action ownership does not reactivate the old continuation', async () => {
  let release, attacks = 0;
  const bot = { equip: () => new Promise(r => { release = r; }), attack: () => { attacks++; } };
  const scope = new ActionScope(bot);
  const old = scope.run(async () => { await bot.equip(); bot.attack(); });
  scope.interrupt();
  scope.run(() => bot.attack());
  release(); await old;
  assert.equal(attacks, 1);
});

test('protection keeps scaffold movement and rejects digging another building', async () => {
  let movement, dug = 0;
  const bot = { pathfinder: { setMovements: m => { movement = m; }, getPathTo: m => m },
    dig: async () => { dug++; }, placeBlock: async () => {} };
  const protection = protectWorld(bot);
  bot.pathfinder.setMovements({ allow1by1towers: true, scafoldingBlocks: [3, 4], exclusionAreasBreak: [] });
  assert.equal(movement.allow1by1towers, true);
  assert.deepEqual(movement.scafoldingBlocks, [3, 4]);
  const block = { name: 'oak_planks', position: new Vec3(1, 64, 1) };
  assert.equal(movement.exclusionAreasBreak[0](block), 100);
  await assert.rejects(bot.dig(block), /protected_block/);
  await protection.permit([block.position], () => bot.dig(block));
  await assert.rejects(bot.dig(block), /protected_block/);
  await bot.placeBlock({ position: block.position.offset(0, -1, 0) }, new Vec3(0, 1, 0));
  await bot.dig(block);
  assert.equal(dug, 2);
});

test('planning delegates the item goal and reads inventory independently', () => {
  const runner = new MindcraftRunner(() => {}, null);
  runner.bot = { entity: {}, registry: { itemsByName: { cobblestone: {} } },
    inventory: { items: () => [{ name: 'cobblestone', count: 3 }] } };
  assert.deepEqual(runner.plan('cobblestone', 8), {
    steps: [{ kind: 'obtain', item: 'cobblestone', count: 8 }], inventory: { cobblestone: 3 } });
  assert.equal(runner.plan('invented_item', 1).error, 'unknown_item');
});

test('internal obtain command requires an explicit resource scope', () => {
  const command = { v: 1, type: 'do', id: 1, skill: 'obtain', args: { item: 'cobblestone', count: 8 } };
  assert.equal(parseCommand(JSON.stringify(command)).error, 'bad_args');
  command.args.resource_scope = 'nearby';
  assert.equal(parseCommand(JSON.stringify(command)).cmd.args.resource_scope, 'nearby');
});
