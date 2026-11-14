import test from 'node:test';
import assert from 'node:assert/strict';
import { ActionScope } from '../src/mindcraft/action-scope.js';
import { MindcraftRunner, blockedActions, nativeExit } from '../src/mindcraft/runtime.js';
import { protectWorld } from '../src/mindcraft/protection.js';
import { Vec3 } from 'vec3';
import { parseCommand } from '../src/protocol.js';
import minecraftData from 'minecraft-data';
import { collectBlock } from '../src/vendor/mindcraft/src/agent/library/skills.js';

test('binding a conversation resets native game history and remembered places',async()=>{
  const runner=new MindcraftRunner(()=>{},null);
  runner.agent={name:'SessionTest',history:{turns:[{content:'previous owner'}]},
    memory_bank:{private:true},npc:{data:{goals:[{name:'stone'}],curr_goal:{name:'wood'}}}};
  await runner.bindCore('http://127.0.0.1:12345','x'.repeat(32));
  assert.deepEqual(runner.agent.history.turns,[]);
  assert.equal(runner.agent.history.memory,'');
  assert.equal(runner.agent.memory_bank.private,undefined);
  assert.deepEqual(runner.agent.npc.data.goals,[]);
  assert.equal(runner.agent.npc.data.curr_goal,null);
});

test('closing a core session still detaches locally when the remote host has already closed', async () => {
  const runner = new MindcraftRunner(()=>{},null);
  runner.coreModel = {cancel:async()=>{throw new Error('ECONNREFUSED');}};
  await runner.unbindCore();
  assert.equal(runner.coreModel,null);
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
      return [];
    } };
  protectWorld(bot);
  await collectBlock(bot, 'oak_log', 1);
  assert.equal(searches, 1);
  assert.match(bot.output, /No oak_log nearby/);
});

test('the benchmark body can block extra Mindcraft commands, such as the plan executor', () => {
  const defaults = blockedActions({});
  assert.ok(!defaults.includes('!obtainItem'));
  assert.deepEqual(blockedActions({ CIEL_MINDCRAFT_BLOCKED_ACTIONS: ' !obtainItem, ' }), [...defaults, '!obtainItem']);
  assert.throws(() => blockedActions({ CIEL_MINDCRAFT_BLOCKED_ACTIONS: 'obtainItem' }), /Invalid/);
});

test('the upstream restart after smelting resyncs the inventory instead of disconnecting', async () => {
  const stops = [], synced = [];
  const bot = { inventory: { id: 0 }, _syncWindow: async window => { synced.push(window.id); } };
  const exit = nativeExit(bot, msg => stops.push(msg));
  await exit('Safely restarting to update inventory.');
  assert.deepEqual([stops, synced], [[], [0]]);
  exit('Infinite action loop detected, shutting down.');
  assert.deepEqual(stops, ['Infinite action loop detected, shutting down.']);
  const hung = nativeExit({ inventory: { id: 0 }, _syncWindow: () => new Promise(() => {}) }, msg => stops.push(msg), 10);
  await hung('Safely restarting to update inventory.');
  assert.equal(stops.length, 1);
});

test('a work waits for the reply a mode asks for after interrupting its action', async () => {
  const runner = new MindcraftRunner(() => {}, null);
  const order = [];
  const agent = { shut_up: false, actions: { executing: false }, self_prompter: { loop_active: false, isActive: () => false },
    async handleMessage(source, text) {
      if (source === 'system') {
        await new Promise(r => setTimeout(r, 300));
        order.push('reply'); runner.nativeResponse = 'carried on';
        return;
      }
      order.push('first');
      // The unstuck mode runs as its own action, then calls handleMessage, awaited by no one.
      const mode = new Promise(r => setTimeout(r, 150));
      runner.modeActions.add(mode);
      mode.then(() => runner.modeActions.delete(mode));
      void mode.then(() => agent.handleMessage('system', '(AUTO MESSAGE) interrupted by unstuck'));
    } };
  runner.agent = agent;
  runner.trackReplies(agent);
  runner.coreModel = {};
  runner.activity = () => {};
  runner.bot = { inventory: { items: () => [] } };
  const pending = runner.pursue({ args: { request: 'make a farm' }, token: { cancelled: false } });
  await new Promise(r => setTimeout(r, 10));
  const result = await pending;
  assert.deepEqual(order, ['first', 'reply']);
  assert.equal(result.response, 'carried on');
});

test('a pursue left at a plan choice says so, and the owner speaks into the running pursue', async () => {
  const runner = new MindcraftRunner(() => {}, 'Owner');
  const heard = [];
  let reply;
  const agent = { shut_up: false, actions: { executing: false }, self_prompter: { loop_active: false, isActive: () => false },
    async handleMessage(source, text) {
      heard.push([source, text]);
      if (text === 'shear them') { runner.bot.pendingChoice = null; runner.nativeResponse = 'Shearing them.'; return; }
      runner.bot.pendingChoice = { question: 'how to get 3 white_wool', options: { 'kill:sheep': () => {}, 'shear:sheep': () => {} } };
      runner.nativeResponse = 'Kill or shear?';
      reply = new Promise(r => setTimeout(r, 100));
      await reply;
    } };
  runner.agent = agent;
  runner.trackReplies(agent);
  runner.coreModel = {};
  runner.activity = () => {};
  runner.bot = { inventory: { items: () => [] } };
  const c = { id: 3, skill: 'pursue', args: { request: 'Build a dirt shelter.' }, token: { cancelled: false } };
  runner.current = c;
  const asked = await runner.pursue(c);
  assert.deepEqual(asked.waiting_owner, { choice: 'how to get 3 white_wool', options: ['kill:sheep', 'shear:sheep'] });
  assert.equal(runner.tell(9, 'not this one'), false);
  const again = runner.pursue({ ...c, args: { request: 'shear them' } });
  const done = await again;
  assert.equal(done.waiting_owner, undefined);
  assert.equal(runner.tell(3, 'shear them'), true);
  await new Promise(r => setTimeout(r, 10));
  assert.deepEqual(heard.map(h => h[0]), ['Owner', 'Owner', 'Owner']);
});
