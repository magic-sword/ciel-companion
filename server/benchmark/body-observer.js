// Read-only instrumentation of the real Runner; no alternate movement logic.
import { writeFileSync, renameSync } from 'node:fs';
import { MindcraftRunner as Runner } from '../src/mindcraft/runtime.js';
const attach = Runner.prototype.attach;
Runner.prototype.attach = function (bot) {
  attach.call(this, bot);
  clearInterval(this.benchmarkObserver);
  if (!bot) return;
  this.benchmarkObserver = setInterval(() => {
    if (!bot.entity) return;
    const target = bot.players.Bench_Owner?.entity;
    const state = { t: Date.now() / 1000, body: this.snapshot(),
      motion:{position:bot.entity.position,velocity:bot.entity.velocity,onGround:bot.entity.onGround,controls:bot.controlState,
        physics_enabled:bot.physicsEnabled,target_dig:bot.targetDigBlock?{name:bot.targetDigBlock.name,position:bot.targetDigBlock.position}:null,
        moving:bot.pathfinder.isMoving(),mining:bot.pathfinder.isMining(),building:bot.pathfinder.isBuilding()},
      target_entity_known: Boolean(target && bot.entities[target.id]),
      target_entity_position: target?.position ?? null,
      references: bot.pointing?.latest(bot) ?? null };
    writeFileSync('/app/benchmark-data/body-state.tmp', JSON.stringify(state));
    renameSync('/app/benchmark-data/body-state.tmp', '/app/benchmark-data/body-state.json');
  }, 200);
};
await import('../src/main.js');
