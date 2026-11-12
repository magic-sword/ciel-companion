// Mindcraft owns the body. This adapter translates CIEL's ownership/result contract.
import pf from 'mineflayer-pathfinder';
import { Vec3 } from 'vec3';
import { BodyCommands } from '../body-command.js';
import { executeRegion } from '../spatial.js';
import { protectWorld } from './protection.js';
import { ActionScope } from './action-scope.js';
import { alignPlayerCollision } from '../player-physics.js';
import { confirmedCrafting } from '../craft-sync.js';
import { approachTrackedPlayer } from '../player-locator.js';
import { CielModel } from './ciel-model.js';
import { pursueItem, resolveItemGoal } from './brain.js';
import { setSettings } from '../vendor/mindcraft/src/agent/settings.js';
import { initBot } from '../vendor/mindcraft/src/utils/mcdata.js';
import { ActionManager } from '../vendor/mindcraft/src/agent/action_manager.js';
import { initModes } from '../vendor/mindcraft/src/agent/modes.js';
import * as skills from '../vendor/mindcraft/src/agent/library/skills.js';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
export const atReturnPosition = (position, origin) =>
  Math.abs(position.y-origin.y)<0.75 && position.distanceTo(origin)<=1.5;
const inventory = bot => {
  const counts = {};
  for (const item of bot?.inventory?.items() ?? []) counts[item.name] = (counts[item.name] ?? 0) + item.count;
  return counts;
};
class Failed extends Error {
  constructor(reason, note) { super(reason); this.note = note; }
}
export function createMindcraftBot(options) {
  setSettings({ ...options, minecraft_version: options.version, narrate_behavior: false });
  return initBot(options.username);
}

export class MindcraftRunner extends BodyCommands {
  bindCore(url, token) { this.coreModel = new CielModel(null, url, {token}); }
  async unbindCore() {
    const model=this.coreModel; this.coreModel=null;
    // Revocation already aborts local inference and rejects late results. The
    // conversation API can legitimately have closed before the MCP disconnect.
    try { await model?.cancel(); }
    catch (e) { console.warn('CIEL session closed before cancellation acknowledgement'); }
  }
  constructor(report, owner) {
    super({ report, available: () => Boolean(this.bot?.entity), run: c => this.execute(c),
      halt: () => this.haltExecution() });
    this.owner = owner;
    this.bot = null;
    this.modeActions = new Set();
    this.goalContexts = new Map();
  }

  attach(bot) {
    clearInterval(this.timer);
    this.bot = bot;
    if (!bot) return;
    alignPlayerCollision(bot);
    confirmedCrafting(bot);
    this.blocked = false;
    this.protection = protectWorld(bot);
    this.actionScope = new ActionScope(bot);
    bot.output = '';
    bot.interrupt_code = false;
    bot.lastDamageTime = 0;
    bot.lastDamageTaken = 0;
    let health = bot.health;
    bot.on('health', () => {
      if (bot.health < health) {
        bot.lastDamageTime = Date.now(); bot.lastDamageTaken = health - bot.health;
      }
      health = bot.health;
    });
    bot.autoEat.options = { ...bot.autoEat.options, priority: 'foodPoints', startAt: 14,
      bannedFood: ['rotten_flesh', 'spider_eye', 'poisonous_potato', 'pufferfish', 'chicken'] };
    const agent = this.agent = {
      bot, shut_up: true,
      self_prompter: { isActive: () => false, stopLoop() {} },
      prompter: { getInitModes: () => ({ hunting: false, torch_placing: false, elbow_room: false,
        item_collecting: false, cheat: false, cowardice: false }) },
      npc: { getBuiltPositions: () => [] },
      history: { add() {} },
      isIdle: () => !agent.actions.executing,
      clearBotLogs: () => { bot.output = ''; bot.interrupt_code = Boolean(this.current?.token.cancelled); },
      requestInterrupt: () => this.interrupt(bot),
      cleanKill: () => { this.blocked = true; bot.quit('Mindcraft action did not stop'); },
      // CIEL already receives structured damage/work notifications; never start a second conversation.
      handleMessage() {}, openChat() {},
    };
    agent.actions = new ActionManager(agent);
    const runAction = agent.actions.runAction.bind(agent.actions);
    agent.actions.runAction = (label, fn, options = {}) => {
      if (this.bot !== bot || this.current?.token.cancelled)
        return Promise.resolve({ success: false, interrupted: true });
      const mode = label.startsWith('mode:');
      if (mode) { this.defending = true; this._defenseAt = Date.now(); this.changed(); }
      const promise = runAction(label, () => this.actionScope.run(fn), { ...options, timeout: -1 })
        .then(result => {
          // Native command wrappers return text only. Preserve a runtime exception
          // as failure before it becomes another model-guided exploration attempt.
          if (label.startsWith('action:') && !result.success && !result.interrupted)
            throw new Failed('execution_error', { action: label, detail: result.message?.slice(0, 500) });
          return result;
        });
      if (mode) {
        this.modeActions.add(promise);
        void promise.finally(() => {
          this.modeActions.delete(promise);
          this.defending = this.modeActions.size > 0;
          this.changed();
        });
      }
      return promise;
    };
    initModes(agent);
    let ticking = false;
    this.timer = setInterval(async () => {
      if (ticking || this.bot !== bot || !bot.entity || this.current?.token.cancelled || this.blocked) return;
      ticking = true;
      try { await bot.modes.update(); }
      catch (e) { console.warn('Mindcraft mode failed:', e.message); }
      finally { ticking = false; }
    }, 250);
    this.timer.unref?.();
  }

  interrupt(bot = this.bot) {
    if (!bot) return;
    this.actionScope?.interrupt();
    bot.interrupt_code = true;
    bot.pathfinder.setGoal(null);
    bot.clearControlStates();
    bot.stopDigging();
    bot.pvp.stop();
    void Promise.resolve(bot.collectBlock.cancelTask()).catch(() => {});
  }

  async haltExecution() {
    this.agent?.actions.cancelResume();
    this.interrupt();
    // Physical interruption must not wait for the inference server's acknowledgement.
    await Promise.all([this.coreModel?.cancel(), this.agent?.actions.stop()]);
    await this.waitModes();
    await this.actionScope?.settle();
    this.interrupt();
  }

  async waitModes() {
    while (this.modeActions.size) await Promise.all([...this.modeActions]);
  }

  waitForDefense() { return this.waitModes(); }

  doing() {
    const c = this.current;
    return c ? { id: c.id, skill: c.skill, args: c.args } : null;
  }


  async action(label, run, c) {
    await this.waitModes();
    if (c.token.cancelled) throw new Failed(c.token.reason);
    let value, failure;
    const result = await this.agent.actions.runAction(label, async () => {
      try { value = await run(); } catch(e) { failure=e; throw e; }
    });
    await this.waitModes();
    if (c.token.cancelled) throw new Failed(c.token.reason);
    if (failure) throw failure;
    if (!result.success || result.interrupted) throw new Failed(result.interrupted ? 'interrupted' : 'cannot_continue');
    if (value === false) throw new Failed('objective_unverified');
    return value;
  }


  async pursue(c) {
    if (!this.coreModel) throw new Failed('core_unavailable');
    let context = this.goalContexts.get(c.args.goal_id);
    if (!context) {
      this.activity(c, 'thinking');
      const before = inventory(this.bot), origin = this.bot.entity.position.clone();
      const goal = await resolveItemGoal(this, c.args.request);
      if (c.token.cancelled) throw new Failed(c.token.reason);
      if (goal.clarification) throw new Failed('goal_unclear', goal);
      context = {goal,before,origin,target:goal.quantity+(goal.quantity_mode==='gain'?(before[goal.item]??0):0)};
      this.goalContexts.set(c.args.goal_id,context);
      if(this.goalContexts.size>512)this.goalContexts.delete(this.goalContexts.keys().next().value);
    }
    const {goal,target,origin}=context;
    const command={...c,args:{item:goal.item,resource_scope:goal.resource_scope}};
    let first=context.started?'':goal.command;
    context.started=true;
    try {
      while(!c.token.cancelled) {
        await pursueItem(this,command,target,first); first='';
        if(c.token.cancelled)break;
        this.activity(c, 'returning');
        // A radius of two also accepts the tunnel directly below the starting
        // point. Reach the original standing cell before claiming a return.
        await this.action('ciel:return',()=>skills.goToPosition(this.bot,origin.x,origin.y,origin.z,0),c);
        const observed=inventory(this.bot);
        if((observed[goal.item]??0)>=target && atReturnPosition(this.bot.entity.position,origin))
          return {goal,target,inventory:observed,returned:true};
      }
      throw new Failed(c.token.reason??'stopped');
    } catch(e) {
      const note={...e.note,goal,target,inventory:inventory(this.bot),returned:false};
      throw new Failed(e instanceof Failed?e.message:e.goalReason??'execution_error',note);
    }
  }

  activity(c, stage, command = '') {
    if(!c.token.cancelled)this.report('activity',{id:c.id,request_id:c.request_id,
      command_scope:c.scope??'',stage,command});
  }

  async execute(c) {
    try {
      if (c.skill === 'pursue') return { ok: true, note: await this.pursue(c) };
      const note = await this.action(`ciel:${c.skill}`, () => this.perform(c), c);
      return { ok: true, note };
    } catch (e) {
      return { ok: false, reason: c.token.reason ?? (e instanceof Failed ? e.message : 'error'),
        ...(e.note ? { note: e.note } : {}), ...(e instanceof Failed ? {} : { detail: String(e.message).slice(0, 160) }) };
    } finally {
      await this.waitModes();
      this.interrupt();
      await this.actionScope?.settle();
    }
  }

  async perform(c) {
    const bot = this.bot, a = c.args;
    const player = a.player ?? this.owner;
    if (['follow', 'come', 'give'].includes(c.skill) || a.player) {
      if (!player) throw new Failed('no_owner');
      if (!bot.players[player]?.entity) {
        try { await approachTrackedPlayer(bot,player,c.token,
          (x,z)=>skills.goToGoal(bot,new pf.goals.GoalNearXZ(x,z,2))); }
        catch(e) { throw new Failed(e.message); }
      }
    }
    switch (c.skill) {
      // GoalFollow works on block cells; leave margin for the continuous 3-block arrival contract.
      case 'follow': return skills.followPlayer(bot, player, 2);
      case 'come': return skills.goToPlayer(bot, player, 2);
      case 'go_to':
        if (a.player) return skills.goToPlayer(bot, player, 2);
        return a.y === undefined
          ? skills.goToGoal(bot, new pf.goals.GoalXZ(a.x, a.z))
          : skills.goToPosition(bot, a.x, a.y, a.z, 1);
      case 'give': return skills.giveToPlayer(bot, a.item, player, a.count);
      case 'craft': {
        const before = inventory(bot)[a.item] ?? 0;
        await skills.craftRecipe(bot, a.item, a.count);
        if ((inventory(bot)[a.item] ?? 0) - before < a.count) throw new Failed('missing_materials');
        return { made: a.count };
      }
      case 'collect': {
        const before = inventory(bot);
        await skills.collectBlock(bot, a.block, a.count);
        const after = inventory(bot);
        return { gained: Object.fromEntries(Object.entries(after).map(([name, n]) => [name, n - (before[name] ?? 0)])) };
      }
      case 'find': return skills.goToNearestBlock(bot, a.block, 2, 64);
      case 'edit_region': {
        const plan = bot.regionPlans.start(bot, a.plan_id, c.scope);
        // A verified construction plan owns exact stances and placement faces.
        // Native general-purpose skills may dig/scaffold/reposition, invalidating
        // that plan. Keep the region executor's careful movements and exact edits.
        return executeRegion(bot, plan, c.token, { Failed, watched: (_bot, run) => run(),
          move: s => this.regionMove(bot,s,c),
        }, a.budget_ms);
      }
      case 'pointed_action': return this.pointed(c);
      default: throw new Failed('unsupported_skill');
    }
  }

  async regionMove(bot, stance, c) {
    let previous=bot.entity.position.clone(), last=Date.now();
    const timer=setInterval(()=>{
      const p=bot.entity.position;
      if(p.distanceTo(previous)>0.1){previous=p.clone();last=Date.now();}
      if(c.token.cancelled || Date.now()-last>2000)bot.pathfinder.setGoal(null);
    },100);
    try {return await bot.pathfinder.goto(new pf.goals.GoalBlock(stance.x,stance.y,stance.z));}
    finally {clearInterval(timer);}
  }

  async pointed(c) {
    const bot = this.bot, a = c.args;
    const selection = bot.pointing.resolve(bot, a.selection_id);
    if (!selection) throw new Failed('selection_expired');
    if (selection.points.length !== 1) throw new Failed('selection_needs_one_point');
    const p = selection.points[0];
    const check = () => {
      if (!bot.pointing.resolve(bot, a.selection_id)) throw new Failed('selection_expired');
      if (bot.blockAt(new Vec3(p.x, p.y, p.z))?.name !== p.block) throw new Failed('selection_changed');
    };
    check();
    if (a.action === 'move') return skills.goToPosition(bot, p.x, p.y + 1, p.z, 2);
    if (p.block !== 'crafting_table') throw new Failed('unsupported_selected_block');
    const before = inventory(bot).crafting_table ?? 0;
    await skills.goToPosition(bot, p.x, p.y, p.z, 2);
    if (c.token.cancelled) return;
    check();
    await this.protection.permit([p], () => skills.breakBlockAt(bot, p.x, p.y, p.z));
    // Item entities and inventory packets arrive after the block removal packet.
    for(let attempt=0;attempt<10 && !c.token.cancelled && (inventory(bot).crafting_table??0)<=before;attempt++) {
      await skills.wait(bot,200);
      if(c.token.cancelled)break;
      await skills.pickupNearbyItems(bot);
    }
    if ((inventory(bot).crafting_table ?? 0) <= before) throw new Failed('objective_unverified');
    return { selection_id: selection.id, recovered: 1 };
  }
}
