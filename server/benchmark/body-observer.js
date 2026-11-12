// Read-only instrumentation of the real Runner; no alternate movement or locator logic.
import { writeFileSync, renameSync, readFileSync, existsSync } from 'node:fs';
import { Vec3 } from 'vec3';
import { MindcraftRunner as Runner } from '../src/mindcraft/runtime.js';
import pathfinderPkg from 'mineflayer-pathfinder';
import {carefulMovements} from '../src/movements.js';
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
      hint: bot.playerLocator?.hint('Bench_Owner') ?? null,
      references: bot.pointing?.latest(bot) ?? null };
    const last=this.last;
    if(!this.current&&last?.skill==='edit_region'&&last.result?.reason==='no_path'&&last.result.note?.stance) {
      if(this.probedPlan!==last.args.plan_id) {
        this.probedPlan=last.args.plan_id;
        const [x,y,z]=last.result.note.stance.split(',').map(Number);
        try {
          const probe=bot.pathfinder.getPathTo(carefulMovements(bot),new pathfinderPkg.goals.GoalBlock(x,y,z),500);
          this.pathProbe={status:probe.status,path:probe.path.map(n=>[n.x,n.y,n.z]).slice(0,32)};
        }catch(e){this.pathProbe={error:e.name};}
      }
      state.path_probe=this.pathProbe;
    }
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
