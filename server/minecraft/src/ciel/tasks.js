// Game-owned work. The client sees tasks and decisions, never our recipe/repair loop.
import { randomUUID } from 'node:crypto';
import { shortWhy } from './words.js';

export const TASK_VERSION = 1;
export const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);
const definitions = [{
  name: 'minecraft.pursue_goal', description: 'マイクラで、物を集める・作る・掘ってくるなど、時間をかけて仕上げる作業を頼む。計画と実行はゲームが行う。',
  examples: ['原木を10個集めてきて', '石のツルハシを作ってくれる？', '丸石を掘ってきてほしいな'],
  arguments: {type:'object',additionalProperties:false,required:['request'],properties:{request:{type:'string',minLength:1,maxLength:2000}}},
  constraints: {type:'object',additionalProperties:false,properties:{}},
  handoff: {version:1,argument:'request',constraints:{},seconds:120},
  interpretation: '依頼文をそのまま渡す。品目・数量・材料不足時の方針は現在のゲーム状態と合わせてMindcraftが判断する。',
}];
export const CAPABILITIES=definitions;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const validId = s => typeof s === 'string' && s.length > 0 && s.length <= 160;
const keys = (o, allowed) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).every(k => allowed.includes(k));

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
      : t.state === 'succeeded' ? `Mindcraftの応答処理が終了しました。成果は未検証です。${t.evidence.response??''}`
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
      reason: t.reason, evidence: t.evidence, decision: t.decision, remaining_ms: Math.max(0, t.deadline - this.clock()) });
  }

  changed(t, state, reason = '', evidence = t.evidence) {
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
        || !validArguments || !Number.isFinite(r.budget_ms) || r.budget_ms < 100 || r.budget_ms > 120000) {
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
      evidence: {}, decision: null, deadline: this.clock() + r.budget_ms, repairs: 0, failures: new Map(), generation: 0,
      follow, followStopping: false };
    this.tasks.set(t.id, t); this.requests.set(r.request_id, t); this.active = t;
    // Reject beyond the history bound; never evict a request and execute its retry a second time.
    this.changed(t, 'accepted');
    t.timer = setTimeout(() => { void this.cancel(t.id, 'deadline'); }, Math.max(1, r.budget_ms - Math.min(5000, r.budget_ms / 4)));
    t.timer.unref?.();
    void this.run(t);
    return this.view(t);
  }

  current(t, generation) { return !this.closed && this.active === t && t.generation === generation && t.state === 'running'; }

  activity(event) {
    const t=this.active;
    if(!t || t.state!=='running' || event.request_id!==t.operation
        || !['thinking','executing','returning'].includes(event.stage))return;
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

  async run(t) {
    const generation = ++t.generation;
    this.changed(t, 'running');
    if (!await this.leaveFollow(t,generation) || !this.current(t,generation)) return;
    t.operation=randomUUID();
    const args={request:t.request.arguments.request,goal_id:t.id};
    this.link.notice({kind:'work_action',id:t.operation,task_id:t.id,skill:'pursue',arguments:args});
    try {
      const done=await this.link.runSkill('pursue',args,t.operation,Math.max(1,t.deadline-this.clock()));
      this.link.notice({kind:'work_action_result',id:t.operation,task_id:t.id,result:done});
      if(!this.current(t,generation))return;
      t.evidence={...t.evidence,...done.note};
      const e=t.evidence,b=this.link.body;
      if(done.ok && e.native_finished===true && e.objective_verified===false && b&&!b.current&&!b.pending&&!b.blocked&&!b.owner)
        this.changed(t,'succeeded','',e);
      else if(['unlinked','disconnected','died','replaced','stopped','no_answer','stop_timeout'].includes(done.reason))
        await this.cancel(t.id,done.reason);
      else this.block(t,done.reason||'objective_unverified',e);
    } catch(e) {if(this.current(t,generation))await this.cancel(t.id,'execution_error');}
  }

  block(t, reason, evidence = {}) {
    if (t.request.constraints.failure_policy === 'stop' || evidence.goal?.failure_policy === 'stop') {
      t.evidence = evidence;
      return this.cancel(t.id, reason);
    }
    t.decision = { decision_id: randomUUID(), actions: ['retry', 'cancel'] };
    this.changed(t, 'needs_decision', reason, evidence);
  }

  answer(id, decisionId, action) {
    const t = this.tasks.get(id);
    if (!t || t !== this.active || t.state !== 'needs_decision' || t.decision?.decision_id !== decisionId)
      return { status: 'error', reason: 'stale_decision' };
    if (!['retry', 'cancel'].includes(action)) return { status: 'error', reason: 'invalid_decision' };
    if (action === 'cancel') return this.cancel(id);
    // Retry cannot change constraints, reset deadline, or loop without bound.
    if (t.repairs++ >= 3 || this.clock() >= t.deadline - 5000) return this.cancel(id, 'repair_budget');
    t.decision = null;
    void this.run(t);
    return this.view(t);
  }

  cancel(id, reason = 'requested') {
    const t = this.tasks.get(id);
    if (!t) return Promise.resolve({ status: 'error', reason: 'unknown_task' });
    if (TERMINAL.has(t.state)) return Promise.resolve(this.view(t));
    if (t.stopping) return t.stopping;
    t.generation++; t.decision = null;
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
