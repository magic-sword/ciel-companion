import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionScope } from '../src/mindcraft/action-scope.js';
import { MindcraftRunner, atReturnPosition } from '../src/mindcraft/runtime.js';
import { protectWorld } from '../src/mindcraft/protection.js';
import { Vec3 } from 'vec3';
import { parseCommand } from '../src/protocol.js';
import minecraftData from 'minecraft-data';
import { collectBlock } from '../src/vendor/mindcraft/src/agent/library/skills.js';

test('return verification rejects a tunnel beneath the original standing cell', () => {
  const origin=new Vec3(0.5,64,0.5);
  assert.equal(atReturnPosition(new Vec3(0.57,62.024,0.499),origin),false);
  assert.equal(atReturnPosition(new Vec3(0.5,63,0.5),origin),false);
  assert.equal(atReturnPosition(new Vec3(0.6,64,0.5),origin),true);
  assert.equal(atReturnPosition(new Vec3(3.5,64,0.5),origin),false);
});

test('closing a core session still detaches locally when the remote host has already closed', async () => {
  const runner = new MindcraftRunner(()=>{},null);
  runner.coreModel = {cancel:async()=>{throw new Error('ECONNREFUSED');}};
  await runner.unbindCore();
  assert.equal(runner.coreModel,null);
});

test('CIEL action failures survive the native action manager result wrapper', async () => {
  const runner=new MindcraftRunner(()=>{},null);
  runner.agent={actions:{async runAction(label,fn) {
    try {await fn();return {success:true};}catch{return {success:false};}
  }}};
  const error=new Error('objective_unverified');
  await assert.rejects(runner.action('ciel:test',async()=>{throw error;},{token:{cancelled:false}}),e=>e===error);
});

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
  assert.equal(bot.cielCanBreak({ name: 'oak_planks', position: null }), false);
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

test('stop reaches the native action manager even while inference cancellation is pending', async () => {
  const runner = new MindcraftRunner(() => {}, null);
  let release, interrupted = false, stopped = false;
  runner.coreModel = { cancel: () => new Promise(r => { release = r; }) };
  runner.interrupt = () => { interrupted = true; };
  runner.agent = { actions: { cancelResume() {}, async stop() { stopped = true; } } };
  const halt = runner.halt();
  assert.equal(interrupted, true);
  assert.equal(stopped, true);
  release();
  await halt;
});

test('native collection tolerates Mineflayer palette entries before checking actual blocks', async () => {
  let searches = 0;
  const bot = { registry: minecraftData('1.21.11'), output: '',
    pathfinder: { setMovements() {}, getPathTo() {} }, dig() {}, placeBlock() {},
    findBlocks({ matching }) {
      searches++;
      assert.equal(matching({ name: 'oak_planks', position: null }), false);
      assert.equal(matching({ name: 'oak_log', position: null }), true);
      // A real world block must still pass the CIEL permission check.
      bot.cielCanBreak = () => false;
      assert.equal(matching({ name: 'oak_log', position: new Vec3(1, 64, 1) }), false);
      return [];
    } };
  protectWorld(bot);
  await collectBlock(bot, 'oak_log', 1);
  assert.equal(searches, 1);
  assert.match(bot.output, /No oak_log nearby/);
});
