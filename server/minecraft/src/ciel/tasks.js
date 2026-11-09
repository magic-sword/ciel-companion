// Game-owned work. The client sees tasks and decisions, never our recipe/repair loop.
import { randomUUID } from 'node:crypto';
import { stepsFrom, skillFor, stepResult, repair } from './goals.js';
import { ja, shortWhy } from './words.js';

export const TASK_VERSION = 1;
export const TERMINAL = new Set(['succeeded', 'failed', 'cancelled']);
export const CAPABILITIES = [{
  name: 'minecraft.obtain_item', description: '材料を必要な分だけ集めて物を用意する。採集も製作もゲームが計画する。',
  arguments: { type: 'object', additionalProperties: false, required: ['item', 'quantity', 'quantity_mode'],
    properties: { item: { type: 'string', pattern: '^[a-z_]+$', description: 'Minecraftの物のID。木のつるはし=wooden_pickaxe、石のつるはし=stone_pickaxe、オークの原木=oak_log。日本語名とIDが対応するときは確認不要。' }, quantity: { type: 'integer', minimum: 1, maximum: 64 },
      quantity_mode: { enum: ['inventory_target', 'gain'] } } },
  constraints: { type: 'object', required: ['resource_scope', 'failure_policy'], additionalProperties: false,
    properties: { resource_scope: { enum: ['nearby', 'search'] }, failure_policy: { enum: ['ask', 'stop'] } } },
  interpretation: '採集はgain、用意・製作はinventory_target。手近な材料で難しければ中止する依頼はnearbyとfailure_policy=stop、60秒。通常はsearchとask、90秒。探索や石の道具は120秒。',
}];
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
    const item = ja(t.request.arguments.item);
    const message = t.state === 'succeeded' ? `${item}を${t.target}個用意できました。`
      : t.state === 'cancelled' ? (t.request.constraints.failure_policy === 'stop' && ['not_found', 'missing_materials', 'needs_tool', 'cannot_harvest'].includes(t.reason)
        ? `${ja(Object.keys(t.evidence.needs ?? {})[0] || t.evidence.item || '材料')}が不足して作れません。中止して待っています。` : '作業を中止して待っています。')
      : t.state === 'needs_decision' ? `${item}の用意を止めて待っています。${shortWhy(t.reason, t.evidence)}。続けるか中止するか決めてください。`
      : t.reason === 'stop_unconfirmed' ? '停止を確認できません。新しい作業は始めていません。'
      : t.state === 'failed' ? `${item}を期限内に用意できず、作業を止めました。` : '';
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
    if (!keys(r, ['request_id', 'capability', 'arguments', 'budget_ms', 'constraints']) || !validId(r.request_id)
        || r.capability !== CAPABILITIES[0].name || !keys(r.arguments, ['item', 'quantity', 'quantity_mode'])
        || !/^[a-z_]+$/.test(r.arguments?.item ?? '') || !Number.isInteger(r.arguments?.quantity)
        || r.arguments.quantity < 1 || r.arguments.quantity > 64
        || !['inventory_target', 'gain'].includes(r.arguments.quantity_mode)
        || !Number.isFinite(r.budget_ms) || r.budget_ms < 100 || r.budget_ms > 120000
        || !keys(r.constraints, ['resource_scope', 'failure_policy']) || !['nearby', 'search'].includes(r.constraints.resource_scope)
        || !['ask', 'stop'].includes(r.constraints.failure_policy)) {
      return { status: 'error', reason: 'invalid_request' };
    }
    const signature = JSON.stringify([r.capability, r.arguments, r.constraints]);
    const known = this.requests.get(r.request_id);
    if (known) return known.signature === signature ? this.view(known) : { status: 'error', reason: 'request_id_conflict' };
    if ((this.active && !TERMINAL.has(this.active.state)) || this.link.body?.blocked
        || this.link.body?.current || this.link.body?.pending || this.link.body?.owner) return { status: 'busy' };
    if (!this.link.playing()) return { status: 'unavailable' };
    if (this.tasks.size >= 512) return { status: 'error', reason: 'session_request_limit' };
    const t = { id: randomUUID(), request: structuredClone(r), signature, revision: 0, state: 'accepted', reason: '',
      evidence: {}, decision: null, deadline: this.clock() + r.budget_ms, repairs: 0, failures: new Map(), generation: 0 };
    this.tasks.set(t.id, t); this.requests.set(r.request_id, t); this.active = t;
    // Reject beyond the history bound; never evict a request and execute its retry a second time.
    this.changed(t, 'accepted');
    t.timer = setTimeout(() => { void this.cancel(t.id, 'deadline'); }, Math.max(1, r.budget_ms - Math.min(5000, r.budget_ms / 4)));
    t.timer.unref?.();
    void this.run(t);
    return this.view(t);
  }

  current(t, generation) { return !this.closed && this.active === t && t.generation === generation && t.state === 'running'; }

  async run(t) {
    const generation = ++t.generation;
    this.changed(t, 'running');
    try {
      const a = t.request.arguments;
      let plan = await this.link.plan(a.item, a.quantity);
      if (!this.current(t, generation)) return;
      if (plan.error) return this.block(t, plan.error);
      if (t.target == null) t.target = a.quantity + (a.quantity_mode === 'gain' ? (plan.inventory[a.item] ?? 0) : 0);
      let have = plan.inventory[a.item] ?? 0;
      if (have >= t.target) return this.changed(t, 'succeeded', '', { inventory: plan.inventory, target: t.target });
      if (t.target - have !== a.quantity) plan = await this.link.plan(a.item, t.target - have);
      if (!this.current(t, generation)) return;
      if (plan.error) return this.block(t, plan.error);
      let steps = stepsFrom(plan.steps), index = 0;
      while (this.current(t, generation) && index < steps.length) {
        const step = steps[index], skill = skillFor(step);
        if (!skill) return this.block(t, 'unsupported_step', { item: step.args.item });
        t.operation = randomUUID();
        this.link.notice({ kind: 'work_action', id: t.operation, task_id: t.id, skill: skill[0], arguments: skill[1] });
        const done = await this.link.runSkill(skill[0], skill[1], t.operation, Math.max(1, t.deadline - this.clock()));
        this.link.notice({ kind: 'work_action_result', id: t.operation, task_id: t.id, result: done });
        if (!this.current(t, generation)) return;
        const result = stepResult(step, done);
        step.progress = result.progress;
        if (result.complete) { index++; continue; }
        if (['unlinked', 'disconnected', 'died', 'replaced', 'stopped', 'no_answer', 'stop_timeout'].includes(result.reason)) {
          return this.cancel(t.id, result.reason);
        }
        const signature = JSON.stringify([step.kind, step.args, result.reason]);
        const failures = (t.failures.get(signature) ?? 0) + 1;
        t.failures.set(signature, failures);
        if (t.repairs++ < 6 && failures <= 2) {
          // A nearby-only request must never silently turn into an exploration task.
          const allowed = result.reason !== 'not_found' || t.request.constraints.resource_scope === 'search';
          if (allowed) {
            const fresh = await this.link.plan(a.item, Math.max(1, t.target - (this.link.state?.inventory?.[a.item] ?? 0)));
            if (!this.current(t, generation)) return;
            let fixed = repair({ spec: { make: a.item }, step, result, remaining: steps.slice(index) }, () => fresh);
            // An execution's concrete shortages can be more precise than a plan's table visibility.
            // Even if replanning returns the same labels, obtain these resources before retrying.
            if (!fixed && ['no_table', 'missing_materials'].includes(result.reason) && Object.keys(result.note?.needs ?? {}).length) {
              const needed = Object.entries(result.note.needs).filter(([, count]) => Number.isInteger(count) && count > 0 && count <= 64);
              if (needed.length) fixed = { steps: [...stepsFrom(needed.map(([item, count]) => ({ kind: 'gather', item, count }))), ...steps.slice(index)] };
            }
            if (fixed) { steps = fixed.steps; index = 0; continue; }
          }
        }
        return this.block(t, result.reason || 'cannot_continue', { ...result.note, item: step.args.item });
      }
      if (!this.current(t, generation)) return;
      // plan returns a fresh inventory read in the body process, independent of speech/skill ok.
      const final = await this.link.plan(a.item, 1);
      if (!this.current(t, generation)) return;
      have = final.inventory?.[a.item] ?? 0;
      if (!final.error && have >= t.target) this.changed(t, 'succeeded', '', { inventory: final.inventory, target: t.target });
      else this.block(t, final.error || 'objective_unverified', { inventory: final.inventory ?? {}, target: t.target });
    } catch (e) {
      if (this.current(t, generation)) await this.cancel(t.id, 'execution_error');
    }
  }

  block(t, reason, evidence = {}) {
    if (t.request.constraints.failure_policy === 'stop') {
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
    this.link.stop(undefined, t.operation);
    const until = this.clock() + this.stopMs;
    while (this.clock() < until) {
      const b = this.link.body;
      if (b && !b.current && !b.pending && !b.blocked) {
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
