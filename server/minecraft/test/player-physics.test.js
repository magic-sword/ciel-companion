import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { test } from 'node:test';
import { Vec3 } from 'vec3';
import { alignPlayerCollision } from '../src/player-physics.js';

const require = createRequire(import.meta.url);
const registry = require('prismarine-registry')('1.21.11');
const World = require('prismarine-world')(registry);
const Chunk = require('prismarine-chunk')(registry);
const { Physics, PlayerState } = require('prismarine-physics');

for (const [dx, dz, yaw] of [[0, 1, Math.PI], [0, -1, 0], [1, 0, -Math.PI / 2], [-1, 0, Math.PI / 2]]) {
  test(`wall contact matches server collision bounds: ${dx},${dz}`, () => {
    const world = new World(() => new Chunk()).sync;
    for (const x of [-1, 0]) for (const z of [-1, 0]) world.setColumn(x, z, new Chunk());
    const stone = registry.blocksByName.stone.defaultState;
    for (let x = -3; x <= 3; x++) for (let z = -3; z <= 3; z++) world.setBlockStateId(new Vec3(x, 63, z), stone);
    world.setBlockStateId(new Vec3(dx, 64, dz), stone);
    const environment = { getBlock: p => world.getBlock(p) };
    function contact(aligned) {
      const bot = { version: '1.21.11', inventory: { slots: [] }, jumpTicks: 0, jumpQueued: false,
        entity: { position: new Vec3(0.5, 64, 0.5), velocity: new Vec3(0, 0, 0), onGround: true, yaw, pitch: 0, effects: {} },
        physics: Physics(registry, environment) };
      if (aligned) alignPlayerCollision(bot);
      const controls = { forward: true, back: false, left: false, right: false, jump: false, sprint: false, sneak: false };
      for (let i = 0; i < 20; i++) bot.physics.simulatePlayer(new PlayerState(bot, controls), environment).apply(bot);
      const p = dx ? bot.entity.position.x : bot.entity.position.z;
      const direction = dx || dz;
      const serverHalfWidth = Math.fround(0.6) / 2;
      return direction > 0 ? p + serverHalfWidth - 1 : serverHalfWidth - p;
    }
    assert.ok(contact(false) > 0, 'old physics overlaps the wall according to server dimensions');
    assert.ok(contact(true) <= 0, 'aligned physics stops outside the server wall');
  });
}
