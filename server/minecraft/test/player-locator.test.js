import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { PlayerLocator, approachTrackedPlayer } from '../src/player-locator.js';
import { Runner } from '../src/skills.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const { createSerializer, createDeserializer } = require('minecraft-protocol');
const uuid = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';

test('Mindcraft locator approach uses bounded steps and requires a visible player', async () => {
  const bot = {players:{Owner:{}},entity:{position:new Vec3(0,64,0)},
    playerLocator:{hint:()=>({x:100,z:0,source:'vec3i'})},pathfinder:{setGoal(){}}};
  const moves=[];
  await approachTrackedPlayer(bot,'Owner',{cancelled:false},async(x,z)=>{
    moves.push([x,z]);bot.players.Owner.entity={position:new Vec3(100,64,0)};
  });
  assert.deepEqual(moves,[[16,0]]);
  delete bot.players.Owner.entity;
  bot.playerLocator.hint=()=>null;
  await assert.rejects(approachTrackedPlayer(bot,'Owner',{cancelled:false},()=>assert.fail('must not move')),/player_not_visible/);
  await assert.rejects(approachTrackedPlayer(bot,'Owner',{cancelled:true,reason:'stopped'},()=>assert.fail('must not move')),/stopped/);
});

function fixture() {
  const bot = new EventEmitter();
  Object.assign(bot, {
    _client: new EventEmitter(), registry,
    players: { Owner: { uuid } }, entities: {},
    entity: { position: new Vec3(0, 64, 0) },
    inventory: { items: () => [] },
    waitForTicks: async () => {},
    dig: async () => {},
    pathfinder: { setMovements() {}, setGoal() {}, stop() {}, goto: async () => {} },
    collectBlock: { cancelTask: async () => {} },
  });
  bot.playerLocator = new PlayerLocator(bot);
  const packet = (type, data, operation = 'track', id = uuid) => bot._client.emit('tracked_waypoint', {
    operation, waypoint: { hasUUID: true, uuid: id, type, data },
  });
  const show = () => {
    const entity = { id: 7, position: new Vec3(40, 64, 0) };
    bot.players.Owner.entity = entity;
    bot.entities[entity.id] = entity;
    return entity;
  };
  const runner = new Runner(() => {}, 'Owner');
  runner.attach(bot);
  const run = (skill = 'come') => runner.start({ id: 1, skill, args: {} });
  return { bot, packet, show, runner, run };
}

test('ロケータの方角は公式サーバーのyawラジアン（南0・東-π/2・北π・西π/2）', () => {
  const { bot, packet } = fixture();
  for (const [angle, x, z] of [[0, 0, 16], [-Math.PI / 2, 16, 0], [Math.PI, 0, -16], [Math.PI / 2, -16, 0]]) {
    packet('azimuth', angle);
    const hint = bot.playerLocator.hint('Owner');
    assert.ok(Math.abs(hint.x - x) < 1e-6);
    assert.ok(Math.abs(hint.z - z) < 1e-6);
    assert.equal(hint.y, undefined);
  }
});

test('名前に対応するUUIDだけを使い、チャンク情報を正確な座標に昇格しない', () => {
  const { bot, packet } = fixture();
  packet('vec3i', { x: 50, y: 80, z: -20 }, 'track', other);
  assert.equal(bot.playerLocator.hint('Owner'), null);
  packet('chunk', { chunkX: -2, chunkZ: 3 });
  assert.deepEqual(bot.playerLocator.hint('Owner'), { x: -24, z: 56, source: 'chunk' });
  delete bot.players.Owner;
  assert.equal(bot.playerLocator.hint('Owner'), null);
});

test('取消・空の通知・不正値で手掛かりを捨てる', () => {
  const { bot, packet } = fixture();
  for (const [type, data, operation] of [['empty', undefined, 'update'], ['azimuth', NaN, 'update'], ['azimuth', 0, 'untrack']]) {
    packet('azimuth', 0);
    packet(type, data, operation);
    assert.equal(bot.playerLocator.hint('Owner'), null);
  }
});

test('死亡・ディメンション変更・退出・切断で手掛かりを残さない', () => {
  const { bot, packet } = fixture();
  for (const event of ['death', 'respawn', 'playerLeft', 'end']) {
    packet('azimuth', 0);
    bot.emit(event, { uuid });
    assert.equal(bot.playerLocator.hint('Owner'), null);
  }
  assert.equal(bot._client.listenerCount('tracked_waypoint'), 0);
});

test('方向から短く進み、プレイヤーを取得したら通常の接近へ切り替える', async () => {
  const { bot, packet, show, runner, run } = fixture();
  packet('azimuth', -Math.PI / 2);
  const goals = [];
  bot.pathfinder.goto = async goal => { goals.push(goal); show(); };
  await run();
  assert.equal(goals.length, 2);
  assert.equal(goals[0].x, 16);
  assert.equal(goals[0].y, undefined);
  assert.equal(goals[1].x, 40);
  assert.equal(runner.last.result.ok, true);
});

test('手掛かり地点に着いただけでは成功にせず、期限で終了する', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1000 });
  const { bot, packet, runner, run } = fixture();
  packet('chunk', { chunkX: 0, chunkZ: 0 });
  bot.pathfinder.goto = async goal => { bot.entity.position = new Vec3(goal.x, 64, goal.z); };
  bot.waitForTicks = async () => t.mock.timers.tick(60001);
  await run();
  assert.equal(runner.last.result.ok, false);
  assert.equal(runner.last.result.reason, 'player_search_timeout');
});

test('方向通知がなければ移動せず、座標不足を返す', async () => {
  const { bot, runner, run } = fixture();
  let moves = 0;
  bot.pathfinder.goto = async () => { moves++; };
  await run();
  assert.equal(moves, 0);
  assert.equal(runner.last.result.reason, 'player_not_visible');
});

test('探索中に手掛かりが消えたら経路を止めて失敗を返す', async () => {
  const { bot, packet, runner, run } = fixture();
  packet('azimuth', 0);
  let reject;
  bot.pathfinder.goto = () => new Promise((_, r) => { reject = r; packet('empty', undefined, 'untrack'); });
  bot.pathfinder.setGoal = () => reject?.(new Error('GoalChanged'));
  await run();
  assert.equal(runner.last.result.reason, 'player_not_visible');
  assert.equal(runner.current, null);
});

test('探索の停止後に到着や次の経路を発行しない', async () => {
  const { bot, packet, runner, run } = fixture();
  packet('azimuth', 0);
  let reject, started;
  const ready = new Promise(r => { started = r; });
  let moves = 0;
  bot.pathfinder.goto = () => { moves++; started(); return new Promise((_, r) => { reject = r; }); };
  bot.pathfinder.setGoal = () => reject?.(new Error('GoalChanged'));
  const moving = run();
  await ready;
  await runner.stop('stopped');
  await moving;
  assert.equal(moves, 1);
  assert.equal(runner.last.result.reason, 'stopped');
  assert.equal(runner.last.result.ok, false);
});

test('追従開始時も方向探索を使える', async () => {
  const { bot, packet, show, runner, run } = fixture();
  packet('vec3i', { x: 40, y: 64, z: 0 });
  bot.pathfinder.goto = async () => { show(); };
  const goals = [];
  bot.pathfinder.setGoal = goal => {
    if (goal) { goals.push(goal); setImmediate(() => { void runner.stop('stopped'); }); }
  };
  await run('follow');
  assert.equal(goals.length, 1);
  assert.equal(runner.last.result.ok, true);
});

test('実際の1.21.11パケットのデコード結果を受信できる', () => {
  const { bot } = fixture();
  const serializer = createSerializer({ state: 'play', isServer: true, version: '1.21.11' });
  const parser = createDeserializer({ state: 'play', isServer: false, version: '1.21.11' });
  for (const [type, data] of [['azimuth', -Math.PI / 2], ['vec3i', { x: 100, y: 64, z: -50 }], ['chunk', { chunkX: -4, chunkZ: 8 }], ['empty', undefined]]) {
    const wire = serializer.createPacketBuffer({ name: 'tracked_waypoint', params: {
      operation: 'track', waypoint: { hasUUID: true, uuid, icon: { style: 'minecraft:default' }, type, data },
    } });
    const decoded = parser.parsePacketBuffer(wire).data;
    bot._client.emit(decoded.name, decoded.params);
    assert.equal(bot.playerLocator.hint('Owner')?.source ?? null, type === 'empty' ? null : type);
  }
});

test('道がなければ探索を成功にせずno_pathを返す', async () => {
  const { bot, packet, runner, run } = fixture();
  packet('azimuth', 0);
  bot.pathfinder.goto = async () => { throw new Error('NoPath'); };
  await run();
  assert.equal(runner.last.result.reason, 'no_path');
});

test('静止していて通知が長く来なくても、表示が取り消されるまでは手掛かりが有効', t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1000 });
  const { bot, packet } = fixture();
  packet('azimuth', 0);
  t.mock.timers.tick(120000);
  assert.equal(bot.playerLocator.hint('Owner').source, 'azimuth');
});

test('追従中に見失っても、方向から探し直して再取得した相手についていく', async () => {
  const { bot, packet, show, runner, run } = fixture();
  show();
  packet('azimuth', 0);
  let following = 0, searches = 0;
  bot.pathfinder.setGoal = goal => {
    if (!goal) return;
    following++;
    if (following === 1) { delete bot.entities[7]; delete bot.players.Owner.entity; }
    else setImmediate(() => { void runner.stop('stopped'); });
  };
  bot.pathfinder.goto = async () => { searches++; show(); };
  await run('follow');
  assert.equal(searches, 1);
  assert.equal(following, 2);
  assert.equal(runner.last.result.ok, true);
});
