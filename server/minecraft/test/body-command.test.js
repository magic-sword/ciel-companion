import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BodyCommands, commandBot } from '../src/body-command.js';
import { CielLink } from '../src/ciel/link.js';

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const turn = () => new Promise(r => setImmediate(r));
const cmd = id => ({ id, skill: 'follow', args: {} });

test('切り替えは旧処理と停止の後片付けの両方を待つ', async () => {
  const old = deferred(), cleanup = deferred(), ran = [];
  const body = new BodyCommands({ report: () => {}, halt: () => cleanup.promise,
    run: async c => { ran.push(c.id); if (c.id === 1) await old.promise; return { ok: true }; } });
  const one = body.start(cmd(1)), two = body.start(cmd(2));
  assert.equal(body.snapshot().current.phase, 'stopping');
  old.resolve(); await turn();
  assert.deepEqual(ran, [1]);
  cleanup.resolve(); await Promise.all([one, two]);
  assert.deepEqual(ran, [1, 2]);
});

test('停止中の再依頼は最新だけを始め、遅い対象指定停止は次の作業を止めない', async () => {
  const old = deferred(), next = deferred(), ran = [], events = [];
  const body = new BodyCommands({ report: (type, data) => events.push({ type, ...data }),
    run: async c => { ran.push(c.id); await (c.id === 1 ? old.promise : next.promise); return { ok: true }; } });
  const one = body.start(cmd(1)), two = body.start(cmd(2)), three = body.start(cmd(3));
  old.resolve(); await turn();
  assert.deepEqual(ran, [1, 3]);
  await body.stop('stopped', 1);
  assert.equal(body.current.token.cancelled, false);
  next.resolve(); await Promise.all([one, two, three]);
  assert.equal(events.find(e => e.type === 'done' && e.id === 2).reason, 'replaced');
});

test('切り替え先が材料不足でも、旧追従の停止を確定する', async () => {
  const old = deferred();
  const body = new BodyCommands({ report: () => {}, prepare: c => c.id === 2 ? { reason: 'missing_materials' } : null,
    run: async () => { await old.promise; return { ok: true }; } });
  const one = body.start(cmd(1)), two = body.start({ ...cmd(2), skill: 'craft' });
  old.resolve(); await Promise.all([one, two]);
  assert.equal(body.current, null);
  assert.equal(body.last.result.reason, 'missing_materials');
});

test('停止期限を超えたら次を開始せず、停止確認まで所有権を保持する', async () => {
  const old = deferred(), ran = [], events = [];
  const body = new BodyCommands({ stopMs: 15, report: (type, data) => events.push({ type, ...data }),
    run: async c => { ran.push(c.id); await old.promise; return { ok: true }; } });
  const one = body.start(cmd(1)), two = body.start(cmd(2));
  await new Promise(r => setTimeout(r, 35));
  assert.equal(body.blocked, true);
  assert.deepEqual(ran, [1]);
  await body.start(cmd(3));
  assert.equal(events.find(e => e.type === 'error' && e.id === 3).reason, 'stop_timeout');
  old.resolve(); await Promise.all([one, two]);
  assert.equal(body.blocked, false);
});

test('同じ命令IDの再送は実行を増やさない', async () => {
  let runs = 0;
  const body = new BodyCommands({ report: () => {}, run: async () => { runs++; return { ok: true }; } });
  const one = body.start(cmd(1)), repeated = body.start(cmd(1));
  await Promise.all([one, repeated]);
  await body.start(cmd(2)); await body.start(cmd(1));
  assert.equal(runs, 2);
});

test('会話の世代が替わったら同じ数値IDも新規命令になり、古い停止は干渉しない', async () => {
  const old = deferred(), next = deferred(), ran = [];
  const body = new BodyCommands({ report: () => {}, run: async c => {
    ran.push(c.scope); await (c.scope === 'old' ? old.promise : next.promise); return { ok: true };
  } });
  const one = body.start({ ...cmd(1), scope: 'old' }), two = body.start({ ...cmd(1), scope: 'new' });
  old.resolve(); await turn();
  await body.stop('stopped', 1, 'old');
  assert.equal(body.current.token.cancelled, false);
  next.resolve(); await Promise.all([one, two]);
  assert.deepEqual(ran, ['old', 'new']);
});

test('防御は発行済みの操作を待ち、防御中の新しい通常操作を止める', async () => {
  const equipped = deferred(), started = deferred(), after = deferred();
  const actions = [];
  const bot = { equip: async () => { actions.push('equip'); started.resolve(); await equipped.promise; },
    craft: async () => actions.push('craft') };
  const body = new BodyCommands({ report: () => {}, run: async c => {
    const scoped = commandBot(bot, c, body);
    await scoped.equip(); await scoped.craft(); after.resolve(); return { ok: true };
  } });
  const done = body.start(cmd(1)); await started.promise;
  let owns = false;
  const defense = body.defense(true).then(() => { owns = true; });
  await turn(); assert.equal(owns, false);
  equipped.resolve(); await defense; await turn();
  assert.deepEqual(actions, ['equip']);
  await body.defense(false); await after.promise; await done;
  assert.deepEqual(actions, ['equip', 'craft']);
});

test('防御の終了待ちはキャンセルでき、停止した依頼は操作を発行しない', async () => {
  const body = new BodyCommands({ report: () => {}, run: async () => { throw new Error('must not run'); } });
  await body.defense(true);
  const done = body.start(cmd(1));
  await body.stop('stopped', 1); await done;
  assert.equal(body.current, null);
  await body.defense(false);
});

test('食事中に受けた命令は食事終了を待つ', async () => {
  const meal = deferred(), ran = [];
  const body = new BodyCommands({ report: () => {}, run: async c => { ran.push(c.id); return { ok: true }; } });
  const eating = body.maintain(() => meal.promise);
  const task = body.start(cmd(1)); await turn();
  assert.deepEqual(ran, []);
  meal.resolve(); await Promise.all([eating, task]);
  assert.deepEqual(ran, [1]);
});

test('同期的な開始・終了でもCielLinkが終了通知を失わず、同じ題の新規依頼は通る', async () => {
  const events = [], commands = [];
  const link = new CielLink({ notice: e => events.push(e), command: raw => {
    const c = JSON.parse(raw); commands.push(c);
    link.send(JSON.stringify({ type: 'started', id: c.id }));
    link.send(JSON.stringify({ type: 'done', id: c.id, ok: true }));
  } });
  const first = await link.do('follow'), second = await link.do('follow');
  assert.equal(events.length, 2);
  assert.equal(events[0].session, first.session);
  assert.notEqual(first.task, second.task);
  assert.equal(commands.length, 2);
});

test('目的の停止はその依頼だけを対象にし、到着が遅い段も開始させない', async () => {
  const commands = [];
  const link = new CielLink({ command: raw => commands.push(JSON.parse(raw)) });
  link.stop(undefined, 'old-step');
  assert.equal((await link.runSkill('follow', {}, 'old-step')).reason, 'stopped');
  assert.equal(commands.length, 0);
  const started = link.runSkill('follow', {}, 'new-step');
  const repeated = link.runSkill('follow', {}, 'new-step');
  assert.equal(commands.length, 1);
  const id = commands[0].id;
  link.send(JSON.stringify({ type: 'accepted', id }));
  link.stop(undefined, 'old-step');
  assert.equal(commands.length, 1);
  link.stop(undefined, 'new-step');
  assert.equal(commands.at(-1).task, id);
  link.send(JSON.stringify({ type: 'done', id, ok: false, reason: 'stopped' }));
  await Promise.all([started, repeated]);
});
