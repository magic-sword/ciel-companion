// Reproduce Mindcraft crafting step by step on the dedicated benchmark world and compare the
// body's inventory with the server's (RCON) after every step, with the inventory packets.
// Run inside the body-bench image while body-bench itself is stopped (it uses Ciel_Debug):
//   docker compose ... run --rm --no-deps -e CIEL_BENCH_RCON_PASSWORD body-bench \
//     node benchmark/craft-probe.js [--no-sync] [--obtain stone_pickaxe [--trace]] [--out /app/benchmark-data/craft-probe.jsonl]
// --obtain runs the !obtainItem plan executor from nothing, with three oak trees and stone below;
// --trace also logs the start and end of every dig, equip, collect and path call.
// Mutations follow the benchmark rules: marked world only, under an exclusive lease.
import net from 'node:net';
import { randomUUID } from 'node:crypto';
import { appendFileSync, writeFileSync } from 'node:fs';
import { once } from 'node:events';
import { createMindcraftBot } from '../src/mindcraft/runtime.js';
import { confirmedCrafting } from '../src/craft-sync.js';
import * as skills from '../src/vendor/mindcraft/src/agent/library/skills.js';
import * as world from '../src/vendor/mindcraft/src/agent/library/world.js';
import { obtainItem } from '../src/vendor/mindcraft/src/agent/library/obtain.js';

const args = process.argv.slice(2);
const SYNC = !args.includes('--no-sync');
const OUT = args[args.indexOf('--out') + 1] && args.includes('--out')
  ? args[args.indexOf('--out') + 1] : '/app/benchmark-data/craft-probe.jsonl';
const OBTAIN = args.includes('--obtain') ? args[args.indexOf('--obtain') + 1] : null;
const TRACE = args.includes('--trace');
const PLAYER = 'Ciel_Debug', MARKER = 'ciel-benchmark-v1';
const ITEMS = ['oak_log', 'oak_planks', 'stick', 'crafting_table', 'wooden_pickaxe', 'cobblestone', 'stone_pickaxe'];
writeFileSync(OUT, '');
const record = (kind, data = {}) => appendFileSync(OUT, JSON.stringify({ t: Date.now(), kind, ...data }) + '\n');

class Rcon {
  constructor(password) { this.password = password; this.id = 10; this.buffer = Buffer.alloc(0); this.waiting = []; }
  async open() {
    this.socket = net.connect(25576, '127.0.0.1');
    await once(this.socket, 'connect');
    this.socket.on('close', () => this.waiting.splice(0).forEach(resolve => resolve({ id: -1, body: '', closed: true })));
    this.socket.on('data', chunk => {
      this.buffer = Buffer.concat([this.buffer, chunk]);
      while (this.buffer.length >= 4) {
        const size = this.buffer.readInt32LE(0);
        if (this.buffer.length < size + 4) break;
        const id = this.buffer.readInt32LE(4), body = this.buffer.subarray(12, size + 2).toString('utf8');
        this.buffer = this.buffer.subarray(size + 4);
        this.waiting.shift()?.({ id, body });
      }
    });
    const auth = await this.send(3, this.password);
    if (auth.closed) throw new Error('RCON closed the connection (server not ready?)');
    if (auth.id === -1) throw new Error('RCON authentication failed');
  }
  send(type, text) {
    const body = Buffer.from(text, 'utf8'), id = ++this.id, packet = Buffer.alloc(14 + body.length);
    packet.writeInt32LE(10 + body.length, 0); packet.writeInt32LE(id, 4); packet.writeInt32LE(type, 8);
    body.copy(packet, 12);
    const reply = new Promise(resolve => this.waiting.push(resolve));
    this.socket.write(packet);
    return reply;
  }
  async command(text) { return (await this.send(2, text)).body; }
}

const rcon = new Rcon(process.env.CIEL_BENCH_RCON_PASSWORD);
await rcon.open();
if (!(await rcon.command('data get storage ciel_benchmark:meta suite')).trim().endsWith(`"${MARKER}"`))
  throw new Error('Not a marked benchmark world; refusing to modify it');
const lease = randomUUID().replaceAll('-', '');
await rcon.command(`execute unless data storage ciel_benchmark:meta active run data modify storage ciel_benchmark:meta active set value "${lease}"`);
if (!(await rcon.command('data get storage ciel_benchmark:meta active')).trim().endsWith(`"${lease}"`))
  throw new Error('Benchmark world is already leased');

const server = async () => {
  const counts = {};
  for (const item of ITEMS) {
    const text = await rcon.command(`clear ${PLAYER} minecraft:${item} 0`);
    counts[item] = Number(text.match(/Found (\d+)/)?.[1] ?? 0);
  }
  return counts;
};
const client = bot => {
  const counts = world.getInventoryCounts(bot);
  return Object.fromEntries(ITEMS.map(item => [item, counts[item] ?? 0]));
};

let bot;
try {
  bot = createMindcraftBot({ host: '127.0.0.1', port: 25566, username: PLAYER, auth: 'offline', version: '1.21.11' });
  await once(bot, 'spawn');
  bot.output = '';
  // Mindcraft's placeBlock consults modes; the probe runs none of them.
  bot.modes = { isOn: () => false, pause() {}, unpause() {}, unPauseAll() {} };
  if (SYNC) confirmedCrafting(bot);
  // Inventory packets in arrival order, and our clicks, to locate any divergence.
  bot._client.on('packet', (data, meta) => {
    if (['set_slot', 'window_items', 'set_cursor_item', 'set_player_inventory'].includes(meta.name))
      record('packet', { name: meta.name, windowId: data.windowId, stateId: data.stateId, slot: data.slot,
        item: data.item?.itemId ?? data.item?.itemCount, count: data.items?.filter(i => i?.itemCount).length });
  });
  const write = bot._client.write.bind(bot._client);
  bot._client.write = (name, params) => {
    if (name === 'window_click') record('click', { windowId: params.windowId, stateId: params.stateId, slot: params.slot,
      button: params.mouseButton, mode: params.mode });
    return write(name, params);
  };
  for (const command of [`gamemode creative ${PLAYER}`, `tp ${PLAYER} 0.5 85 0.5`, 'forceload add -48 -48 48 48',
    'fill -8 63 -8 8 63 8 minecraft:grass_block', 'fill -8 64 -8 8 70 8 minecraft:air', `clear ${PLAYER}`,
    `tp ${PLAYER} 0.5 64 0.5 0 0`, `gamemode survival ${PLAYER}`,
    ...(OBTAIN ? ['fill -8 60 -8 8 62 8 minecraft:stone', 'fill 4 64 3 4 67 3 minecraft:oak_log[axis=y]',
      'fill -4 64 3 -4 67 3 minecraft:oak_log[axis=y]', 'fill 4 64 -4 4 67 -4 minecraft:oak_log[axis=y]']
      : [`give ${PLAYER} minecraft:oak_log 3`])])
    await rcon.command(command);
  await bot.waitForTicks(20);
  record('start', { sync: SYNC, client: client(bot), server: await server() });
  if (OBTAIN) {
    const began = Date.now();
    let ok, error;
    // Print the executor's log as it goes and never wait past the cap, so a hang shows where it stopped.
    const at = v => v ? `${Math.floor(v.x)},${Math.floor(v.y)},${Math.floor(v.z)}` : '-';
    const trace = text => console.log(`[${((Date.now() - began) / 1000).toFixed(1)}s] * ${text} @${at(bot.entity.position)}`);
    if (TRACE) {
      // Start and end of every dig, equip, collect and path call: a call that never ends is the stall.
      bot.on('path_update', r => trace(`path ${r.status} len=${r.path.length}`));
      bot.on('path_stop', () => trace('path stop'));
      bot.on('playerCollect', (who, item) => { if (who === bot.entity) trace(`picked ${item.getDroppedItem?.()?.name}`); });
      const wrap = (owner, name, label) => {
        const original = owner[name].bind(owner);
        owner[name] = async (...a) => {
          const what = a[0]?.position ? `${a[0].name} ${at(a[0].position)}` : (a[0]?.name ?? a[0]?.constructor?.name ?? '');
          trace(`${label} start ${what}`);
          try { const r = await original(...a); trace(`${label} end`); return r; }
          catch (e) { trace(`${label} threw ${e?.message}`); throw e; }
        };
      };
      wrap(bot, 'dig', 'dig'); wrap(bot, 'equip', 'equip'); wrap(bot.tool, 'equipForBlock', 'equipForBlock');
      wrap(bot.collectBlock, 'collect', 'collect'); wrap(bot.pathfinder, 'goto', 'goto');
    }
    let shown = 0;
    const ticker = setInterval(() => {
      const lines = bot.output.split('\n').filter(Boolean);
      for (const line of lines.slice(shown)) console.log(`[${((Date.now() - began) / 1000).toFixed(1)}s] ${line}`);
      shown = lines.length;
    }, 1000);
    let cap;
    try {
      ok = await Promise.race([obtainItem(bot, OBTAIN, 1),
        new Promise((_, reject) => { cap = setTimeout(() => reject(new Error('probe cap 240s')), 240000); })]);
    } catch (e) { error = String(e.message).slice(0, 200); bot.interrupt_code = true; }
    clearTimeout(cap); clearInterval(ticker);
    record('obtain', { item: OBTAIN, ok, error, seconds: (Date.now() - began) / 1000, output: bot.output.trim(),
      client: client(bot), server: await server() });
  }
  for (const [item, count] of OBTAIN ? [] : [['oak_planks', 3], ['stick', 2], ['crafting_table', 1], ['wooden_pickaxe', 1]]) {
    bot.output = '';
    let ok, error;
    try { ok = await skills.craftRecipe(bot, item, count); } catch (e) { error = String(e.message).slice(0, 200); }
    const immediately = client(bot);
    await bot.waitForTicks(20);
    record('step', { item, count, ok, error, output: bot.output.trim(), client_immediately: immediately,
      client_after_1s: client(bot), server: await server() });
  }
} finally {
  bot?.quit('craft probe finished');
  await rcon.command(`clear ${PLAYER}`);
  await rcon.command(`execute if data storage ciel_benchmark:meta {active:"${lease}"} run data remove storage ciel_benchmark:meta active`);
  rcon.socket.end();
}
process.exit(0);
