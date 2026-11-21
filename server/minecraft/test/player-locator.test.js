import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { PlayerLocator, approachTrackedPlayer } from '../src/player-locator.js';

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
  return { bot, packet, show };
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

test('静止していて通知が長く来なくても、表示が取り消されるまでは手掛かりが有効', t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1000 });
  const { bot, packet } = fixture();
  packet('azimuth', 0);
  t.mock.timers.tick(120000);
  assert.equal(bot.playerLocator.hint('Owner').source, 'azimuth');
});

