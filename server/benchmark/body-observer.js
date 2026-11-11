// Read-only instrumentation of the real Runner; no alternate movement or locator logic.
import { writeFileSync, renameSync, readFileSync, existsSync } from 'node:fs';
import { Vec3 } from 'vec3';
import { Runner } from '../src/skills.js';
const attach = Runner.prototype.attach;
Runner.prototype.attach = function (bot) {
  attach.call(this, bot);
  clearInterval(this.benchmarkObserver);
  if (!bot) return;
  this.benchmarkObserver = setInterval(() => {
    if (!bot.entity) return;
    const target = bot.players.Bench_Owner?.entity;
    const state = { t: Date.now() / 1000, body: this.snapshot(),
      target_entity_known: Boolean(target && bot.entities[target.id]),
      target_entity_position: target?.position ?? null,
      hint: bot.playerLocator?.hint('Bench_Owner') ?? null,
      references: bot.pointing?.latest(bot) ?? null };
    const watch='/app/benchmark-data/spatial-watch.json';
    if (existsSync(watch)) {
      const request=JSON.parse(readFileSync(watch,'utf8'));
      state.spatial = { id:request.id, blocks:request.cells.map(p=>bot.blockAt(new Vec3(...p))?.name ?? null) };
    }
    writeFileSync('/app/benchmark-data/body-state.tmp', JSON.stringify(state));
    renameSync('/app/benchmark-data/body-state.tmp', '/app/benchmark-data/body-state.json');
  }, 200);
};
await import('../src/main.js');
