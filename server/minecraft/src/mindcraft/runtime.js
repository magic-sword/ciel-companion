// Mindcraft owns the body. This adapter translates CIEL's ownership/result contract.
import { BodyCommands } from '../body-command.js';
import { ActionScope } from './action-scope.js';
import { alignPlayerCollision } from '../player-physics.js';
import { confirmedCrafting } from '../craft-sync.js';
import { CielModel } from './ciel-model.js';
import { SessionModel } from './session-model.js';
import { cacheLayout } from './prompt-layout.js';
import { executeCommand, blacklistCommands } from '../vendor/mindcraft/src/agent/commands/index.js';
import defaultSettings from '../vendor/mindcraft/settings.js';
import { setSettings } from '../vendor/mindcraft/src/agent/settings.js';
import { initBot } from '../vendor/mindcraft/src/utils/mcdata.js';
import { initModes } from '../vendor/mindcraft/src/agent/modes.js';

const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const inventory = bot => {
  const counts = {};
  for (const item of bot?.inventory?.items() ?? []) counts[item.name] = (counts[item.name] ?? 0) + item.count;
  return counts;
};
class Failed extends Error {
  constructor(reason, note) { super(reason); this.note = note; }
}
// Extra commands to block, e.g. '!obtainItem' to measure Mindcraft without the plan executor.
export function blockedActions(env = process.env) {
  const extra = (env.CIEL_MINDCRAFT_BLOCKED_ACTIONS || '').split(',').map(name => name.trim()).filter(Boolean);
  if (extra.some(name => !/^![A-Za-z]+$/.test(name))) throw new Error('Invalid CIEL_MINDCRAFT_BLOCKED_ACTIONS');
  return [...new Set([...defaultSettings.blocked_actions, ...extra])];
}

// Upstream Mindcraft restarts its process after a successful !smeltItem only to refresh the
// inventory. CIEL owns the connection, so it resyncs the inventory window and keeps playing;
// every other exit request still stops the body.
const INVENTORY_RESTART = 'Safely restarting to update inventory.';
export function nativeExit(bot, stop, timeoutMs = 3000) {
  return msg => {
    if (msg !== INVENTORY_RESTART) return stop(msg);
    if (typeof bot._syncWindow !== 'function') return;
    let timer;
    const expired = new Promise(resolve => { timer = setTimeout(resolve, timeoutMs); });
    return Promise.race([bot._syncWindow(bot.inventory), expired])
      .catch(e => console.warn('Inventory resync failed:', e.message)).finally(() => clearTimeout(timer));
  };
}

export function createMindcraftBot(options) {
  setSettings({ ...defaultSettings, ...options, blocked_actions: blockedActions(), minecraft_version: options.version });
  return initBot(options.username);
}

export class MindcraftRunner extends BodyCommands {
  async bindCore(url, token) {
    await this.ready;
    const old=this.coreModel;
    if(old) {await this.stop('rebound');this.coreModel=null;await old.cancel();}
    if(this.agent) {
      const { History }=await import('../vendor/mindcraft/src/agent/history.js');
      const { MemoryBank }=await import('../vendor/mindcraft/src/agent/memory_bank.js');
      this.agent.history=new History(this.agent);
      this.agent.memory_bank=new MemoryBank();
      this.agent.npc.data.goals=[];this.agent.npc.data.curr_goal=null;
    }
    const model = new CielModel(null, url, {token});
    this.coreModel = model;
    if(!this.agent || !this.referenceTemplate) return {status:'unavailable'};
    const reference = await this.agent.prompter.replaceStrings(this.referenceTemplate, []);
    return model.prepareReference(reference);
  }
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
  }

  attach(bot) {
    clearInterval(this.timer);
    this.bot = bot;
    if (!bot) return;
    alignPlayerCollision(bot);
    confirmedCrafting(bot);
    this.blocked = false;
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
    this.ready = this.initializeAgent(bot);
    // Attachment is synchronous for the connection layer; command execution
    // awaits component initialization and receives any startup error.
    this.ready.catch(e => console.warn('Mindcraft initialization failed:', e.message));
  }

  async initializeAgent(bot) {
    const { Agent } = await import('../vendor/mindcraft/src/agent/agent.js');
    const { Task } = await import('../vendor/mindcraft/src/agent/tasks/tasks.js');
    const agent = new Agent();
    const provider = new SessionModel(()=>({model:this.bot===bot?this.coreModel:null,token:this.current?.token}),
      ()=>{if(this.current)this.activity(this.current,'thinking');});
    await agent.initializeComponents({name:bot.username,model:'ciel'}, {chat:provider});
    if(this.bot!==bot)return;
    // Same upstream wording, fixed lines first: CIEL caches them once per bound session.
    const layout=cacheLayout(agent.prompter.profile.conversing);
    agent.prompter.profile.conversing=layout.template;
    this.referenceTemplate=layout.reference;
    this.agent=agent;
    agent.bot=bot;
    agent.onCommand=command=>{if(this.current)this.activity(this.current,'executing',command);};
    agent.task=new Task(agent,null,Date.now());
    const { VisionInterpreter }=await import('../vendor/mindcraft/src/agent/vision/vision_interpreter.js');
    agent.vision_interpreter=new VisionInterpreter(agent,false);
    agent.blocked_actions=blockedActions();
    if(agent.blocked_actions.length>defaultSettings.blocked_actions.length)console.log('Blocked commands:',agent.blocked_actions.join(', '));
    blacklistCommands(agent.blocked_actions);
    // Transport and process lifecycle belong to CIEL; planning belongs to Agent.
    agent.openChat=async message=>{this.nativeResponse=String(message).trim();};
    agent.cleanKill=nativeExit(bot,()=>{this.blocked=true;this.interrupt(bot);bot.quit('Mindcraft stopped');});
    const requestInterrupt=agent.requestInterrupt.bind(agent);
    agent.requestInterrupt=()=>{requestInterrupt();this.actionScope.interrupt();};
    const nativeRun=agent.actions.runAction.bind(agent.actions);
    agent.actions.runAction=(label,fn,options={})=>{
      const c=this.current;
      if(!this.coreModel || c?.token.cancelled)return Promise.resolve({success:false,interrupted:true});
      // Keep upstream results and timeout choices intact. Only revoke stale I/O.
      const pending=nativeRun(label,()=>this.actionScope.run(fn),options);
      this.modeActions.add(pending);
      pending.then(()=>this.modeActions.delete(pending),()=>this.modeActions.delete(pending));
      return pending;
    };
    initModes(agent);
    agent.npc.init();
    bot.on('idle',()=>{
      if(this.coreModel&&!agent.shut_up){bot.clearControlStates();bot.modes.unPauseAll();}
    });
    let ticking=false,previous=Date.now();
    this.timer=setInterval(async()=>{
      if(ticking || this.bot!==bot || !this.coreModel || !bot.entity || this.current?.token.cancelled)return;
      ticking=true;
      const now=Date.now();
      try {await agent.update(now-previous);}
      catch(e){console.warn('Mindcraft update failed:',e.message);}
      finally{previous=now;ticking=false;}
    },300);
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
    this.agent?.shutUp?.();
    if(this.agent?.npc){this.agent.npc.data.goals=[];this.agent.npc.data.curr_goal=null;}
    this.agent?.actions.cancelResume();
    this.interrupt();
    // Physical interruption must not wait for the inference server's acknowledgement.
    await Promise.all([this.coreModel?.cancel(), this.agent?.actions.stop(), this.agent?.self_prompter?.stop()]);
    await this.agent?.self_prompter?.stopLoop();
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


  async pursue(c) {
    if(!this.coreModel)throw new Failed('core_unavailable');
    this.nativeResponse='';
    this.agent.shut_up=false;
    this.activity(c,'thinking');
    // The upstream loop owns interpretation, history, commands and recovery.
    await this.agent.handleMessage(this.owner || 'user',c.args.request);
    while(!c.token.cancelled && (this.agent.actions.executing || this.agent.self_prompter.loop_active
        || this.agent.self_prompter.isActive())) await pause(100);
    if(c.token.cancelled)throw new Failed(c.token.reason??'stopped');
    return {native_finished:true,objective_verified:false,response:this.nativeResponse,
      inventory:inventory(this.bot)};
  }

  activity(c, stage, command = '') {
    if(!c.token.cancelled)this.report('activity',{id:c.id,request_id:c.request_id,
      command_scope:c.scope??'',stage,command});
  }

  async execute(c) {
    try {
      await this.ready;
      if (c.skill === 'pursue') return { ok: true, note: await this.pursue(c) };
      const note = await this.perform(c);
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
    const a=c.args,player=a.player??this.owner;
    const command = c.skill==='follow' ? `!followPlayer(${JSON.stringify(player)}, 3)`
      : c.skill==='come' ? `!goToPlayer(${JSON.stringify(player)}, 3)`
      : c.skill==='go_to' ? (a.player ? `!goToPlayer(${JSON.stringify(player)}, 3)`
        : `!goToCoordinates(${a.x}, ${a.y??this.bot.entity.position.y}, ${a.z}, 1)`)
      : c.skill==='give' ? `!givePlayer(${JSON.stringify(player)}, ${JSON.stringify(a.item)}, ${a.count})`
      : c.skill==='collect' ? `!collectBlocks(${JSON.stringify(a.block)}, ${a.count})`
      : c.skill==='craft' ? `!craftRecipe(${JSON.stringify(a.item)}, ${a.count})`
      : c.skill==='find' ? `!searchForBlock(${JSON.stringify(a.block)}, 64)` : null;
    if(!command)throw new Failed('unsupported_skill');
    // A system source bypasses upstream's user-forced-command shortcut; direct
    // controls are parsed by the native command executor without a second plan.
    return executeCommand(this.agent,command);
  }
}
