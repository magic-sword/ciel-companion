// シエルの体の MCP の入口（src/ciel/）。体はにせもの（命令を受けて決まった返事をする）で、マイクラは使わない。
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { LoggingMessageNotificationSchema, ResourceUpdatedNotificationSchema } from '@modelcontextprotocol/sdk/types.js';

import { makeHub } from '../src/ciel/hub.js';
import { startHttp } from '../src/ciel/mcp.js';
import { doneFor, eventFor, stateText } from '../src/ciel/words.js';
import { repair, skillFor, stepResult, stepsFrom } from '../src/ciel/goals.js';

const STATE = { type: 'state', connected: true, pos: { x: 1, y: 64, z: 2 }, health: 20, food: 20, night: true, raining: false,
  inventory: { oak_log: 3 }, players: [{ name: 'Hakase', distance: 2.1 }], hostiles: [{ name: 'zombie', distance: 6 }],
  doing: null, blocks: { oak_log: 12 }, body: { version: 1, session: 'body-test', revision: 1, current: null, pending: null, last: null } };

// にせものの体：do には started を返し、少しして done を返す。collect cobblestone は needs_tool で断る
function fakeBody() {
  const sent = [];
  let link = null;
  const reply = (m) => setImmediate(() => link?.send(JSON.stringify({ v: 1, ...m })));
  const command = (raw) => {
    const m = JSON.parse(raw);
    sent.push(m);
    if (m.type === 'do' && m.args.block === 'cobblestone') reply({ type: 'error', id: m.id, reason: 'needs_tool', note: { tool: 'wooden_pickaxe' } });
    else if (m.type === 'do') {
      reply({ type: 'started', id: m.id });
      setTimeout(() => reply({ type: 'done', id: m.id, ok: true, note: { gained: { [m.args.block ?? 'x']: m.args.count ?? 1 } } }), 30);
    } else if (m.type === 'plan') reply({ type: 'planned', id: m.id, steps: [{ kind: 'gather', item: 'oak_log', count: 3 }, { kind: 'craft', item: 'wooden_pickaxe', count: 1 }] });
    else if (m.type === 'look') reply({ type: 'seen', id: m.id, jpeg: Buffer.from('jpeg').toString('base64'), facing: 'north' });
  };
  const hub = makeHub({
    command, owner: 'Hakase',
    onClaim: (l) => { link = l; l.send(JSON.stringify({ v: 1, type: 'hello', owner: 'Hakase', state: STATE })); },
    onRelease: () => { link = null; },
  });
  return { hub, sent, state: (s) => link?.send(JSON.stringify({ v: 1, ...s })) };
}

async function connect(port, onEvent = () => {}, onUpdated = () => {}) {
  const client = new Client({ name: 'test', version: '1' });
  client.setNotificationHandler(LoggingMessageNotificationSchema, (n) => n.params.logger === 'ciel.event' && onEvent(n.params.data));
  client.setNotificationHandler(ResourceUpdatedNotificationSchema, (n) => onUpdated(n.params.uri));
  await client.connect(new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${port}/mcp`)));
  return client;
}

const call = async (c, name, args = {}) => JSON.parse((await c.callTool({ name, arguments: args })).content.at(-1).text);
const until = async (fn, ms = 2000) => {
  const end = Date.now() + ms;
  while (!fn()) {
    if (Date.now() > end) throw new Error('timeout');
    await new Promise((r) => setTimeout(r, 10));
  }
};

test('MCP：道具の印・受け持ち・技の終わりの知らせ・様子・目的の段', async () => {
  const body = fakeBody();
  const http = startHttp(body.hub, { host: '127.0.0.1', port: 0, idleMs: 60000, log: () => {} });
  await new Promise((r) => http.once('listening', r));
  const port = http.address().port;
  const events = [], updated = [];
  const a = await connect(port, (e) => events.push(e), (u) => updated.push(u));
  const b = await connect(port);
  try {
    // 道具には役目と振り分けの例文が付いている
    const tools = (await a.listTools()).tools;
    const collect = tools.find((t) => t.name === 'minecraft_collect_blocks');
    assert.equal(collect._meta['ciel/role'], 'act');
    assert.equal(collect._meta['ciel/long_running'], true);
    assert.ok(collect._meta['ciel/triggers'].length > 0);
    assert.equal(tools.find((t) => t.name === 'minecraft_facts')._meta['ciel/role'], 'know');
    assert.ok(tools.every((t) => t.name.startsWith('minecraft_')));

    const profile = JSON.parse((await a.readResource({ uri: 'game://profile' })).contents[0].text);
    assert.equal(profile.label, 'マイクラ');
    assert.ok(new RegExp(profile.route_words).test('ついてきて'));
    assert.ok((await a.getPrompt({ name: 'play' })).messages[0].content.text.includes('minecraft_facts'));

    // 受け持つ前は体を動かせない。受け持てるのは 1 つだけ
    assert.equal((await call(a, 'minecraft_follow_me')).status, 'unavailable');
    assert.equal((await call(a, 'minecraft_link', { on: true })).status, 'linked');
    assert.equal((await call(b, 'minecraft_link', { on: true })).status, 'busy');
    assert.equal((await call(b, 'minecraft_follow_me')).status, 'busy');

    // 様子
    const st = JSON.parse((await a.readResource({ uri: 'game://state' })).contents[0].text);
    assert.equal(st.playing, true);
    assert.equal(st.body.version, 1);
    assert.equal(Object.hasOwn(st, 'doing'), false);
    assert.equal(st.body.current, null);
    assert.match(st.text, /Hakase（持ち主）/);

    // 技を始めて、終わりは知らせで届く。同じ頼みは二重に受けない
    const r = await call(a, 'minecraft_collect_blocks', { block: 'oak_log', count: 2 });
    assert.equal(r.status, 'started');
    assert.equal(r.title, 'oak_log を 2 個集める');
    await until(() => events.some((e) => e.kind === 'task_done'));
    const done = events.find((e) => e.kind === 'task_done');
    assert.equal(done.task, r.task);
    assert.equal(done.card, 'done');
    assert.match(done.say, /できた（oak_log×2）/);

    // 断られたら、理由の文と次の手
    const no = await call(a, 'minecraft_collect_blocks', { block: 'cobblestone', count: 3 });
    assert.equal(no.status, 'error');
    assert.match(no.why, /掘る道具が無い.*wooden_pickaxe/);
    assert.ok(no.next);

    // 景色の絵は MCP の絵で返る
    const seen = await a.callTool({ name: 'minecraft_look_at_view', arguments: {} });
    assert.equal(seen.content[0].type, 'image');
    assert.equal(JSON.parse(seen.content[1].text).facing, '北');

    // 目的の段：計画・実行・確かめ
    const plan = await call(a, 'minecraft_goal_plan', { spec: { make: 'wooden_pickaxe', count: 1 } });
    assert.deepEqual(plan.steps.map((s) => s.label), ['オークの原木を 3 個集める', '木のツルハシを作る']);
    const stepDone = await call(a, 'minecraft_goal_step', { step: plan.steps[0] });
    assert.deepEqual(stepDone.progress, [3, 3]);
    assert.equal(stepDone.complete, true);

    // 様子が変わったら知らせる
    body.state({ ...STATE, health: 12 });
    await until(() => updated.includes('game://state'));

    // 離したら、もう 1 つの会話が受け持てる
    assert.equal((await call(a, 'minecraft_link', { on: false })).status, 'off');
    assert.equal((await call(b, 'minecraft_link', { on: true })).status, 'linked');
  } finally {
    await a.close();
    await b.close();
    http.close();
  }
});

test('言葉：出来事の選び方と、技の終わり', () => {
  assert.equal(eventFor({ kind: 'hurt', amount: 1, health: 18 }), null);   // 小さなダメージは言わない
  assert.equal(eventFor({ kind: 'hurt', amount: 5, health: 12 }).urgency, 'urgent');
  assert.equal(eventFor({ kind: 'defeated', name: 'zombie' }).memorable, 'マイクラで zombie を倒した');
  assert.equal(eventFor({ kind: 'night' }), null);
  const stopped = doneFor({ ok: false, reason: 'stopped' }, '持ち主についていく');
  assert.equal(stopped.say, undefined);
  assert.equal(stopped.card_note, 'やめた');
  const failed = doneFor({ ok: false, reason: 'missing_materials', note: { needs: { oak_log: 2 } } }, '木のツルハシを作る');
  assert.equal(failed.failed, true);
  assert.match(failed.say, /足りない物：oak_log×2.*次の手：/);
  assert.match(stateText(null, null, false), /つながっていない/);
});

test('目的の段：数が足りない・別の物を数えた・探す段を足す・同じ計画なら直さない', () => {
  const [gather] = stepsFrom([{ kind: 'gather', item: 'cobblestone', count: 3 }]);
  const part = stepResult({ ...gather, progress: [0, 3] }, { ok: true, note: { gained: { cobblestone: 1, dirt: 2 } } });
  assert.equal(part.ok, false);
  assert.equal(part.reason, 'not_found');
  assert.deepEqual(part.progress, [1, 3]);
  const fixed = repair({ spec: { make: 'stone_pickaxe' }, step: gather, result: { reason: 'not_found' }, remaining: [gather] }, () => ({}));
  assert.equal(fixed.steps[0].kind, 'find');
  const same = repair({ spec: { make: 'stone_pickaxe' }, step: gather, result: { reason: 'missing_materials' }, remaining: [gather] },
    () => ({ steps: [{ kind: 'gather', item: 'cobblestone', count: 3 }] }));
  assert.equal(same, null);
});

test('振り分けの例文：心に渡す道具と、相手の発言で呼ぶ目的の道具には、きっかけがある', async () => {
  // 道具を足したら、きっかけも書く（スキルのトリガーと同じ。書き忘れると、その頼みは意味では心へ回らない）
  const body = fakeBody();
  const http = startHttp(body.hub, { host: '127.0.0.1', port: 0, idleMs: 60000, log: () => {} });
  await new Promise((r) => http.once('listening', r));
  const c = await connect(http.address().port);
  try {
    const shown = (await c.listTools()).tools.filter((t) => ['act', 'look', 'know'].includes(t._meta?.['ciel/role']));
    assert.deepEqual(shown.filter((t) => !t._meta['ciel/triggers']?.length).map((t) => t.name), []);
    const p = JSON.parse((await c.readResource({ uri: 'game://profile' })).contents[0].text);
    for (const g of ['start_goal', 'stop_goal', 'resume_goal', 'goal_status']) assert.ok(p.goal_triggers[g]?.length, g);
    assert.ok(p.talker_examples.length > 10);
  } finally {
    await c.close();
    http.close();
  }
});

test('目的の段：2 本で見える所に無くなったら、探してから残りだけ集める', () => {
  const [gather, craft] = stepsFrom([{ kind: 'gather', item: 'oak_log', count: 3 }, { kind: 'craft', item: 'wooden_pickaxe', count: 1 }]);
  const r = stepResult(gather, { ok: true, note: { gained: { oak_log: 2 }, short: 'not_found' } });
  assert.equal(r.complete, false);
  assert.deepEqual(r.progress, [2, 3]);
  const kept = { ...gather, progress: r.progress };
  const fixed = repair({ spec: { make: 'wooden_pickaxe' }, step: kept, result: r, remaining: [kept, craft] }, () => ({}));
  assert.deepEqual(fixed.steps.map((s) => s.kind), ['find', 'gather', 'craft']);
  assert.equal(fixed.text, 'オークの原木が見える所に無いので、探す段を足した');
  assert.deepEqual(skillFor(fixed.steps[1]), ['collect', { block: 'oak_log', count: 1 }]);
});
