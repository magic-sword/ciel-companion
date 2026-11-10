// Read-only instrumentation of the real Runner; no alternate movement or locator logic.
import { writeFileSync, renameSync } from 'node:fs';
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
      hint: bot.playerLocator?.hint('Bench_Owner') ?? null };
    writeFileSync('/app/benchmark-data/body-state.tmp', JSON.stringify(state));
    renameSync('/app/benchmark-data/body-state.tmp', '/app/benchmark-data/body-state.json');
  }, 200);
};
await import('../src/main.js');
