// Game-owned work. The client sees tasks and decisions, never our recipe/repair loop.
import { randomUUID } from 'node:crypto';
import { shortWhy } from './words.js';

export const TASK_VERSION = 1;
export const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);
const definitions = [{
  name: 'minecraft.pursue_goal', description: 'マイクラで、物を集める・作る・掘ってくる、家や農場を作るなど、時間をかけて仕上げる作業を頼む。計画と実行はゲームが行う。',
  arguments: {type:'object',additionalProperties:false,required:['request'],properties:{request:{type:'string',minLength:1,maxLength:2000}}},
  constraints: {type:'object',additionalProperties:false,properties:{}},
  handoff: {version:1,argument:'request',constraints:{},seconds:120},
  interpretation: '依頼文をそのまま渡す。品目・数量・材料不足時の方針は現在のゲーム状態と合わせてMindcraftが判断する。',
}];
export const CAPABILITIES=definitions;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
// One work may run up to 30 minutes: a house from nothing is wood, tools, a bed from sheep that
// must be found, and a hundred blocks. The conversation's handoff asks for 120 s; a plan the
// body makes may lengthen the work to its own estimate (estimate()), within this ceiling.
export const MAX_BUDGET_MS = 1800000;
const validId = s => typeof s === 'string' && s.length > 0 && s.length <= 160;
// The owner's words handed into a work (a reply to its question, or a change of mind).
const MESSAGE_CHARS = 2000;
const validMessage = s => typeof s === 'string' && s.trim().length > 0 && s.length <= MESSAGE_CHARS;
// Replies to the body's questions within one work; each one runs the body again.
const MAX_REPLIES = 8;
// While the work waits for the owner (a question, or a failure to retry or cancel), the body is
// not working: its time does not run, and it starts again from what was left when the owner
// answers. A wait the owner never answers ends the work after this long.
export const OWNER_WAIT_MS = 600000;
const keys = (o, allowed) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).every(k => allowed.includes(k));

// plan v1: what the body's executor is doing, as a graph for people to see. Fields are bounded
// and the vocabulary closed, so a display never shows more than a fact the body reported.
export const PLAN_KINDS = ['obtain', 'make', 'build', 'find', 'wait', 'decide', 'do'];
export const PLAN_STATES = ['pending', 'ready', 'running', 'done', 'failed', 'waiting_choice'];
const text = (s, n) => (typeof s === 'string' ? s : '').slice(0, n);
export function checkedPlan(p) {
  if (!p || typeof p !== 'object' || p.v !== 1 || !validId(p.plan_id) || !Number.isInteger(p.revision) || p.revision < 1
      || !Array.isArray(p.nodes)) return null;
  const nodes = p.nodes.slice(0, 64).filter(n => n && validId(n.id) && PLAN_KINDS.includes(n.kind) && PLAN_STATES.includes(n.state))
    .map(n => ({ id: n.id, parent: validId(n.parent) ? n.parent : null, kind: n.kind, label: text(n.label, 80), state: n.state,
      needs: Array.isArray(n.needs) ? n.needs.filter(validId).slice(0, 8) : [],
      estimate_s: Number.isFinite(n.estimate_s) && n.estimate_s >= 0 ? Math.round(n.estimate_s) : -1,   // -1: not estimated (a number for every client)
      choice: n.choice && typeof n.choice === 'object' ? { question: text(n.choice.question, 120),
        options: (Array.isArray(n.choice.options) ? n.choice.options : []).slice(0, 6).map(o => ({ id: text(o?.id, 40), summary: text(o?.summary, 200) })),
        chosen: typeof n.choice.chosen === 'string' ? text(n.choice.chosen, 40) : null } : null }));
  const ids = new Set(nodes.map(n => n.id));
  return { v: 1, plan_id: p.plan_id, revision: p.revision, title: text(p.title, 80), finished: Boolean(p.finished),
    nodes, current: (Array.isArray(p.current) ? p.current : []).filter(id => ids.has(id)).slice(0, 8) };
}

export class GameTasks {
  constructor(link, { clock = () => performance.now(), stopMs = 4500 } = {}) {
    this.link = link;
    this.clock = clock;
    this.stopMs = stopMs;
    this.tasks = new Map();
    this.requests = new Map();
    this.active = null;
    this.closed = false;
  }

  view(t = this.active) {
    if (!t) return null;
    let message = t.reason === 'stop_unconfirmed' ? '停止を確認できません。新しい作業は始めていません。'
      : t.state === 'succeeded' && t.evidence.goal_done ? `体が作業を終えたと言いました。成果は未検証です。${t.evidence.response??''}`
      : t.state === 'succeeded' ? `Mindcraftの応答処理が終了しました。成果は未検証です。${t.evidence.response??''}`
      : t.state === 'failed' && t.reason === 'stalled' ? `体が行動を止めて、途中で手を止めました。${t.evidence.response??''}`
      : t.state === 'needs_decision' && t.decision?.kind === 'question' ? `オーナーの返事を待っています。${t.decision.message}`
      : t.state === 'needs_decision' ? `作業を止めて待っています。${t.evidence.clarification || shortWhy(t.reason,t.evidence)}。`
      : t.state === 'cancelled' ? `${shortWhy(t.reason,t.evidence)}。作業を中止して待っています。`
      : t.state === 'failed' ? '期限内に完了できず、作業を止めました。'
      : t.state === 'cancelling' ? '作業の停止を確認しています。'
      : t.evidence.activity?.stage==='thinking' ? '次の行動を考えています。'
      : t.evidence.activity?.stage==='returning' ? '集めた物を持って戻っています。'
      : t.evidence.activity?.command==='!collectBlocks' ? 'ブロックを集めています。'
      : t.evidence.activity?.command==='!craftRecipe' ? '材料から作っています。'
      : t.evidence.activity?.command==='!obtainItem' ? '必要な物を順に集めて作っています。' : '依頼を実行しています。';
    if (t.reason === 'body_changed') message = '準備中に別の動作へ切り替わったため、この作業は開始しませんでした。';
    return structuredClone({ version: TASK_VERSION, session: this.link.session, task_id: t.id, request_id: t.request.request_id, message,
      revision: t.revision, state: t.state, capability: t.request.capability, arguments: t.request.arguments,
      reason: t.reason, evidence: t.evidence, decision: t.decision,
      remaining_ms: Math.max(0, t.deadline - (t.waitingSince ?? this.clock())),
      plan: t.plan ?? null });
  }

  changed(t, state, reason = '', evidence = t.evidence) {
    if (state === 'needs_decision') this.wait(t);
    else if (state !== 'cancelling' && !TERMINAL.has(state)) this.resume(t);
    t.state = state; t.reason = reason; t.evidence = evidence; t.revision++;
    this.link.notice({ kind: 'work_state', work: this.view(t) });
    this.link.changed();
    if (TERMINAL.has(state)) clearTimeout(t.timer);
  }

  submit(r) {
    if (this.closed) return { status: 'error', reason: 'unlinked' };
    if(r?.capability==='minecraft.edit_region')return {status:'error',reason:'unsupported_skill'};
    const validArguments=r?.capability===CAPABILITIES[0].name && keys(r.arguments,['request'])
        && typeof r.arguments.request==='string' && r.arguments.request.trim().length>0 && r.arguments.request.length<=2000
        && keys(r.constraints,[]);
    if (!keys(r, ['request_id', 'capability', 'arguments', 'budget_ms', 'constraints']) || !validId(r.request_id)
        || !validArguments || !Number.isFinite(r.budget_ms) || r.budget_ms < 100 || r.budget_ms > MAX_BUDGET_MS) {
      return { status: 'error', reason: 'invalid_request' };
    }
    const signature = JSON.stringify([r.capability, r.arguments, r.constraints]);
    const known = this.requests.get(r.request_id);
    if (known) return known.signature === signature ? this.view(known) : { status: 'error', reason: 'request_id_conflict' };
    const body = this.link.body;
    const follow = body?.current?.skill === 'follow' && body.current.phase !== 'stopping'
      && !body.blocked && !body.pending && !body.owner ? body.current.id : null;
    if ((this.active && !TERMINAL.has(this.active.state)) || body?.blocked
        || (body?.current && follow == null) || body?.pending || body?.owner) return { status: 'busy' };
    if (!this.link.playing()) return { status: 'unavailable' };
    if (this.tasks.size >= 512) return { status: 'error', reason: 'session_request_limit' };
    const t = { id: randomUUID(), request: structuredClone(r), signature, revision: 0, state: 'accepted', reason: '',
      evidence: {}, decision: null, started: this.clock(), deadline: this.clock() + r.budget_ms, repairs: 0, replies: 0, failures: new Map(), generation: 0,
      follow, followStopping: false };
    this.tasks.set(t.id, t); this.requests.set(r.request_id, t); this.active = t;
    // Reject beyond the history bound; never evict a request and execute its retry a second time.
    this.changed(t, 'accepted');
    this.arm(t);
    void this.run(t);
    return this.view(t);
  }

  // Waiting for the owner holds the work's time; the wait itself has its own limit.
  wait(t) {
    if (t.waitingSince != null) return;
    t.waitingSince = this.clock();
    clearTimeout(t.timer);
    t.timer = setTimeout(() => { void this.cancel(t.id, 'owner_no_answer'); }, OWNER_WAIT_MS);
    t.timer.unref?.();
  }

  resume(t) {
    if (t.waitingSince == null) return;
    const waited = this.clock() - t.waitingSince;
    t.waitingSince = null;
    t.deadline += waited; t.started += waited;   // the ceiling counts working time too
    this.arm(t);
  }

  // The stop before the deadline leaves time to confirm the body has stopped.
  arm(t) {
    clearTimeout(t.timer);
    const left = t.deadline - this.clock();
    t.timer = setTimeout(() => { void this.cancel(t.id, 'deadline'); }, Math.max(1, left - Math.min(5000, left / 4)));
    t.timer.unref?.();
  }

  // The body's plan says how long its remaining steps take (the sum of each step's own time, from
  // the plan graph). The work may last that long from now, within the ceiling from its start; an
  // estimate never shortens a work, and a failure never lengthens it.
  estimate(t, seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return;
    const deadline = Math.min(t.started + MAX_BUDGET_MS, this.clock() + seconds * 1000);
    if (deadline <= t.deadline) return;
    t.deadline = deadline;
    this.arm(t);
    this.changed(t, 'running', '', { ...t.evidence, estimate: { seconds: Math.round(seconds) } });
  }

  // The body's plan graph (plan v1), kept checked and bounded for the work view; a newer
  // revision of the same plan, or a new plan, replaces it. Notified apart from the work state,
  // which it does not change.
  plan(t, plan) {
    const clean = checkedPlan(plan);
    if (!clean) return;
    const old = t.plan;
    if (old && old.plan_id === clean.plan_id && clean.revision <= old.revision) return;
    t.plan = clean;
    this.link.notice({ kind: 'work_plan', task_id: t.id, plan: structuredClone(clean) });
    this.link.changed();
  }

  current(t, generation) { return !this.closed && this.active === t && t.generation === generation && t.state === 'running'; }

  activity(event) {
    const t=this.active;
    if(!t || t.state!=='running' || event.request_id!==t.operation)return;
    // What the body says to the owner while it works: told, not kept as the work's state.
    if(event.stage==='said'){
      const text=String(event.text??'').trim().slice(0,600);
      if(text)this.link.notice({kind:'work_message',task_id:t.id,revision:t.revision,text});
      return;
    }
    if(event.stage==='estimate')return this.estimate(t,Number(event.seconds));
    if(event.stage==='plan')return this.plan(t,event.plan);
    if(!['thinking','executing','returning'].includes(event.stage))return;
    const activity={stage:event.stage,command:String(event.command??'').slice(0,64)};
    this.link.notice({kind:'work_activity',task_id:t.id,...activity});
    this.changed(t,'running','',{...t.evidence,activity});
  }

  async leaveFollow(t, generation) {
    if (!this.current(t, generation)) return false;
    if (t.follow == null) return true;
    const b = this.link.body;
    // Never stop a newer command that arrived while planning.
    if (!b || b.blocked || b.pending || b.owner || (b.current && b.current.id !== t.follow)) {
      this.changed(t, 'failed', 'body_changed');
      return false;
    }
    t.followStopping = true;
    this.link.stop(t.follow);
    const until = Math.min(t.deadline, this.clock() + this.stopMs);
    while (this.current(t, generation) && this.clock() < until) {
      const body = this.link.body;
      if (body && !body.current && !body.pending && !body.blocked && !body.owner) {
        t.follow = null;
        return true;
      }
      await pause(25);
    }
    if (this.current(t, generation)) await this.cancel(t.id, 'stop_unconfirmed');
    return false;
  }

  // request: the words the body works from; the owner's reply when a question is answered.
  async run(t, request = t.request.arguments.request) {
    const generation = ++t.generation;
    this.changed(t, 'running');
    if (!await this.leaveFollow(t,generation) || !this.current(t,generation)) return;
    t.operation=randomUUID();
    const args={request,goal_id:t.id};
    this.link.notice({kind:'work_action',id:t.operation,task_id:t.id,skill:'pursue',arguments:args});
    try {
      // The work's own timer stops it at its deadline, which a plan may lengthen; the link's wait
      // only guards the ceiling, so it does not cut off a work that was lengthened.
      const done=await this.link.runSkill('pursue',args,t.operation,Math.max(1,t.started+MAX_BUDGET_MS-this.clock()));
      this.link.notice({kind:'work_action_result',id:t.operation,task_id:t.id,result:done});
      if(!this.current(t,generation))return;
      const {waiting_owner:_asked,...kept}=t.evidence;   // a question belongs to the run that asked it
      t.evidence={...kept,...done.note};
      const e=t.evidence,b=this.link.body;
      const idle=b&&!b.current&&!b.pending&&!b.blocked&&!b.owner;
      // The body stopped at a choice and spoke to the owner instead: the work waits for the reply.
      if(done.ok && e.native_finished===true && e.waiting_owner && idle)
        this.ask(t,e);
      // It stopped acting and talked instead, without saying the work is done: the work ends unfinished, so
      // Ciel (or the owner) decides the next step. Its words go with it.
      else if(done.ok && e.native_finished===true && e.stalled && idle)
        this.changed(t,'failed','stalled',e);
      else if(done.ok && e.native_finished===true && e.objective_verified===false && idle)
        this.changed(t,'succeeded','',e);
      else if(['unlinked','disconnected','died','replaced','stopped','no_answer','stop_timeout'].includes(done.reason))
        await this.cancel(t.id,done.reason);
      else this.block(t,done.reason||'objective_unverified',e);
    } catch(e) {if(this.current(t,generation))await this.cancel(t.id,'execution_error');}
  }

  ask(t, evidence) {
    const waiting = evidence.waiting_owner;
    const message = String(evidence.response || waiting.choice || '').trim().slice(0, 600);
    t.decision = { decision_id: randomUUID(), kind: 'question', actions: ['reply', 'cancel'], message,
      options: Array.isArray(waiting.options) ? waiting.options.slice(0, 12) : [] };
    this.changed(t, 'needs_decision', 'owner_question', evidence);
  }

  block(t, reason, evidence = {}) {
    if (t.request.constraints.failure_policy === 'stop' || evidence.goal?.failure_policy === 'stop') {
      t.evidence = evidence;
      return this.cancel(t.id, reason);
    }
    t.decision = { decision_id: randomUUID(), kind: 'failure', actions: ['retry', 'cancel'] };
    this.changed(t, 'needs_decision', reason, evidence);
  }

  answer(id, decisionId, action, message) {
    const t = this.tasks.get(id);
    if (!t || t !== this.active || t.state !== 'needs_decision' || t.decision?.decision_id !== decisionId)
      return { status: 'error', reason: 'stale_decision' };
    if (!t.decision.actions.includes(action)) return { status: 'error', reason: 'invalid_decision' };
    if (action === 'cancel') return this.cancel(id);
    this.resume(t);
    if (action === 'reply') {
      // The reply carries on the same work: same deadline and constraints, a bounded number of turns.
      if (!validMessage(message)) return { status: 'error', reason: 'invalid_message' };
      if (t.replies++ >= MAX_REPLIES || this.clock() >= t.deadline - 5000) return this.cancel(id, 'reply_budget');
      t.decision = null;
      void this.run(t, message.trim());
      return this.view(t);
    }
    // Retry cannot change constraints, reset deadline, or loop without bound.
    if (t.repairs++ >= 3 || this.clock() >= t.deadline - 5000) return this.cancel(id, 'repair_budget');
    t.decision = null;
    void this.run(t);
    return this.view(t);
  }

  // The owner's words while the body works ("shear them instead"): the body hears them as the
  // owner speaking, and may change its plan. A waiting question is answered with answer(reply).
  tell(id, message) {
    const t = this.tasks.get(id);
    if (!t || t !== this.active || t.state !== 'running' || !t.operation) return { status: 'error', reason: 'not_running' };
    if (!validMessage(message)) return { status: 'error', reason: 'invalid_message' };
    const r = this.link.tell(t.operation, message.trim());
    return r.status === 'told' ? this.view(t) : { status: 'error', reason: r.reason ?? 'not_running' };
  }

  cancel(id, reason = 'requested') {
    const t = this.tasks.get(id);
    if (!t) return Promise.resolve({ status: 'error', reason: 'unknown_task' });
    if (TERMINAL.has(t.state)) return Promise.resolve(this.view(t));
    if (t.stopping) return t.stopping;
    t.generation++; t.decision = null; t.waitingSince = null;
    clearTimeout(t.timer);
    this.changed(t, 'cancelling', reason);
    t.stopping = this.stop(t, reason);
    return t.stopping;
  }

  async stop(t, reason) {
    // A rejected plan has not acquired the body: keep the existing follow alive.
    if (t.follow != null && !t.followStopping && !t.operation) {
      this.changed(t, reason === 'deadline' ? 'failed' : 'cancelled', reason);
      return this.view(t);
    }
    this.link.stop(t.follow ?? undefined, t.operation);
    const until = this.clock() + this.stopMs;
    while (this.clock() < until) {
      const b = this.link.body;
      if (b && !b.current && !b.pending && !b.blocked && !b.owner) {
        this.changed(t, reason === 'deadline' ? 'failed' : 'cancelled', reason);
        return this.view(t);
      }
      await pause(25);
    }
    // Keep ownership and the nonterminal state when stopping cannot be verified.
    this.changed(t, 'cancelling', 'stop_unconfirmed');
    t.stopping = null;
    return this.view(t);
  }

  close() {
    this.closed = true;
    for (const t of this.tasks.values()) { clearTimeout(t.timer); t.generation++; }
  }
}
