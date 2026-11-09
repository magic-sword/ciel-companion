import test from 'node:test';
import assert from 'node:assert/strict';
import { GameTasks } from '../src/ciel/tasks.js';

const request = (extra = {}) => ({ request_id: 'one', capability: 'minecraft.obtain_item',
  arguments: { item: 'stone_pickaxe', quantity: 1, quantity_mode: 'inventory_target' },
  budget_ms: 10000, constraints: { resource_scope: 'search', failure_policy: 'ask' }, ...extra });
const wait = async predicate => {
  for (let i = 0; i < 100; i++) { if (predicate()) return; await new Promise(r => setTimeout(r, 5)); }
  throw new Error('condition did not arrive');
};
function fixture() {
  const link = { session: 'session', state: { inventory: {} }, body: { current: null, pending: null, blocked: false },
    events: [], playing: () => true, changed() {}, notice(e) { this.events.push(e); }, calls: [],
    async plan() { return { steps: [{ kind: 'craft', item: 'stone_pickaxe', count: 1 }], inventory: { ...this.state.inventory } }; },
    async runSkill(skill, args) { this.calls.push([skill, args]); this.state.inventory.stone_pickaxe = 1; return { ok: true }; },
    stop() { this.body.current = null; } };
  const work = new GameTasks(link, { stopMs: 30 });
  return { link, work };
}
test('work verifies final inventory, deduplicates a retry and rejects a conflicting request', async () => {
  const { link, work } = fixture();
  const a = work.submit(request()), b = work.submit(request());
  assert.equal(a.task_id, b.task_id);
  assert.equal(work.submit(request({ arguments: { item: 'oak_log', quantity: 1, quantity_mode: 'gain' } })).reason, 'request_id_conflict');
  await wait(() => work.active.state === 'succeeded');
  assert.equal(link.calls.length, 1);
  assert.equal(work.view().evidence.inventory.stone_pickaxe, 1);
  work.close();
});
test('skill ok without objective evidence is not success', async () => {
  const { link, work } = fixture();
  link.runSkill = async () => ({ ok: true });
  work.submit(request());
  await wait(() => work.active.state === 'needs_decision');
  assert.equal(work.view().reason, 'objective_unverified');
  assert.equal((await work.answer(work.active.id, 'old', 'retry')).reason, 'stale_decision');
  work.close();
});
test('nearby scope does not escalate into find; decision cannot extend deadline', async () => {
  const { link, work } = fixture();
  link.plan = async () => ({ steps: [{ kind: 'gather', item: 'oak_log', count: 3 }], inventory: {} });
  link.runSkill = async (skill) => { link.calls.push(skill); return { ok: false, reason: 'not_found' }; };
  work.submit(request({ constraints: { resource_scope: 'nearby', failure_policy: 'ask' } }));
  await wait(() => work.active.state === 'needs_decision');
  const deadline = work.active.deadline;
  await work.answer(work.active.id, work.active.decision.decision_id, 'retry');
  await wait(() => work.active.state === 'needs_decision');
  assert.equal(work.active.deadline, deadline);
  assert.ok(!link.calls.includes('find'));
  work.close();
});
test('cancellation suppresses delayed plan and permits no new skill', async () => {
  const { link, work } = fixture();
  let resolve;
  link.plan = () => new Promise(r => { resolve = r; });
  work.submit(request());
  const result = await work.cancel(work.active.id);
  assert.equal(result.state, 'cancelled');
  resolve({ steps: [{ kind: 'craft', item: 'stone_pickaxe', count: 1 }], inventory: {} });
  await new Promise(r => setImmediate(r));
  assert.equal(link.calls.length, 0);
  assert.equal(work.active.state, 'cancelled');
  work.close();
});
test('unconfirmed stop retains ownership and refuses overlapping work', async () => {
  const { link, work } = fixture();
  link.runSkill = () => new Promise(() => {});
  work.submit(request());
  link.body.blocked = true;
  const result = await work.cancel(work.active.id);
  assert.equal(result.state, 'cancelling');
  assert.equal(result.reason, 'stop_unconfirmed');
  assert.equal(work.submit(request({ request_id: 'two' })).status, 'busy');
  work.close();
});
test('deadline stops pending planning without a client and rejects malformed conditions', async () => {
  const { link, work } = fixture();
  assert.equal(work.submit(request({ constraints: { resource_scope: 'anywhere' } })).reason, 'invalid_request');
  assert.equal(work.submit(request({ arguments: { item: 'x', quantity: true, quantity_mode: 'gain' } })).reason, 'invalid_request');
  link.plan = () => new Promise(() => {});
  work.submit(request({ budget_ms: 100 }));
  await wait(() => work.active.state === 'failed');
  assert.equal(work.active.reason, 'deadline');
  work.close();
});

test('execution shortage is repaired even when a fresh plan has unchanged labels', async () => {
  const { link, work } = fixture();
  let crafts = 0;
  link.runSkill = async (skill, args) => {
    link.calls.push([skill, args]);
    if (skill === 'craft' && crafts++ === 0) return { ok: false, reason: 'no_table', note: { needs: { oak_log: 1 } } };
    if (skill === 'collect') return { ok: true, note: { gained: { oak_log: 1 } } };
    link.state.inventory.stone_pickaxe = 1;
    return { ok: true };
  };
  work.submit(request());
  await wait(() => work.active.state === 'succeeded');
  assert.deepEqual(link.calls.map(([name]) => name), ['craft', 'collect', 'craft']);
  work.close();
});

test('an explicitly requested practical stop confirms idle body and reports the missing resource', async () => {
  const { link, work } = fixture();
  link.runSkill = async () => ({ ok: false, reason: 'missing_materials', note: { needs: { oak_log: 3 } } });
  work.submit(request({ constraints: { resource_scope: 'nearby', failure_policy: 'stop' } }));
  await wait(() => work.active.state === 'cancelled');
  assert.equal(work.view().reason, 'missing_materials');
  assert.match(work.view().message, /原木/);
  assert.deepEqual(link.calls, []);
  work.close();
});
