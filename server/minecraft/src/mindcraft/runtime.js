// Mindcraft owns the body. This adapter translates CIEL's ownership/result contract.
import pf from 'mineflayer-pathfinder';
import { Vec3 } from 'vec3';
import { BodyCommands } from '../body-command.js';
import { executeRegion } from '../spatial.js';
import { protectWorld } from './protection.js';
import { ActionScope } from './action-scope.js';
import { setSettings } from '../vendor/mindcraft/src/agent/settings.js';
import { initBot } from '../vendor/mindcraft/src/utils/mcdata.js';
import { ActionManager } from '../vendor/mindcraft/src/agent/action_manager.js';
import { initModes } from '../vendor/mindcraft/src/agent/modes.js';
import { ItemGoal } from '../vendor/mindcraft/src/agent/npc/item_goal.js';
import * as skills from '../vendor/mindcraft/src/agent/library/skills.js';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const inventory = bot => {
  const counts = {};
  for (const item of bot.inventory.items()) counts[item.name] = (counts[item.name] ?? 0) + item.count;
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
  constructor(report, owner) {
    super({ report, available: () => Boolean(this.bot?.entity), run: c => this.execute(c),
      halt: () => this.halt() });
    this.owner = owner;
    this.bot = null;
    this.modeActions = new Set();
  }

  attach(bot) {
    clearInterval(this.timer);
    this.bot = bot;
    if (!bot) return;
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
      const promise = runAction(label, () => this.actionScope.run(fn), { ...options, timeout: -1 });
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

  async halt() {
    this.agent?.actions.cancelResume();
    this.interrupt();
    await this.agent?.actions.stop();
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

  plan(item, count) {
    if (!this.bot?.entity) return { error: 'not_spawned' };
    if (!this.bot.registry.itemsByName[item]) return { error: 'unknown_item' };
    return { steps: [{ kind: 'obtain', item, count }], inventory: inventory(this.bot) };
  }

  async action(label, run, c) {
    await this.waitModes();
    if (c.token.cancelled) throw new Failed(c.token.reason);
    let value;
    const result = await this.agent.actions.runAction(label, async () => { value = await run(); });
    await this.waitModes();
    if (c.token.cancelled) throw new Failed(c.token.reason);
    if (!result.success || result.interrupted) throw new Failed(result.interrupted ? 'interrupted' : 'cannot_continue');
    if (value === false) throw new Failed('objective_unverified');
    return value;
  }

  async obtain(c) {
    const bot = this.bot, { item, count, resource_scope } = c.args;
    const before = inventory(bot), target = (before[item] ?? 0) + count;
    const origin = bot.entity.position.clone();
    const goal = new ItemGoal(this.agent);
    this.agent.resource_scope = resource_scope;
    let failures = 0;
    // Recheck after return: scaffold consumption must not be reported as delivered materials.
    while (!c.token.cancelled) {
      await this.waitModes();
      if (c.token.cancelled) break;
      if ((inventory(bot)[item] ?? 0) >= target) {
        await this.action('ciel:return', () => skills.goToPosition(bot, origin.x, origin.y, origin.z, 2), c);
        if ((inventory(bot)[item] ?? 0) >= target)
          return { gained: { [item]: inventory(bot)[item] - (before[item] ?? 0) }, returned: true };
      }
      const progressed = await goal.executeNext(item, Math.max(1, target - (inventory(bot)[item] ?? 0)));
      await this.waitModes();
      if (c.token.cancelled) break;
      failures = progressed ? 0 : failures + 1;
      if (failures >= 3) throw new Failed('not_found', { inventory: inventory(bot), target });
      await pause(25);
    }
    throw new Failed(c.token.reason ?? 'stopped');
  }

  async execute(c) {
    try {
      if (c.skill === 'obtain') return { ok: true, note: await this.obtain(c) };
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
      if (!bot.players[player]?.entity) throw new Failed('player_not_visible');
    }
    switch (c.skill) {
      case 'follow': return skills.followPlayer(bot, player, 3);
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
        // Region validation/verification is a CIEL extension; physical actions use Mindcraft.
        return executeRegion(bot, plan, c.token, { Failed, watched: (_bot, run) => run(),
          move: s => skills.goToGoal(bot, new pf.goals.GoalBlock(s.x, s.y, s.z)),
          dig: p => skills.breakBlockAt(bot, p.x, p.y, p.z),
          place: (p, block) => skills.placeBlock(bot, block, p.x, p.y, p.z),
        }, a.budget_ms);
      }
      case 'pointed_action': return this.pointed(c);
      default: throw new Failed('unsupported_skill');
    }
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
    await skills.pickupNearbyItems(bot);
    if ((inventory(bot).crafting_table ?? 0) <= before) throw new Failed('objective_unverified');
    return { selection_id: selection.id, recovered: 1 };
  }
}
