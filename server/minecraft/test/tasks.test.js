import test from 'node:test';
import assert from 'node:assert/strict';
import { GameTasks, CAPABILITIES } from '../src/ciel/tasks.js';

const request = (extra = {}) => ({ request_id: 'one', capability: 'minecraft.pursue_goal',
  arguments: { request: 'Make a stone pickaxe' },
  budget_ms: 10000, constraints: {}, ...extra });
const wait = async predicate => {
  for (let i = 0; i < 100; i++) { if (predicate()) return; await new Promise(r => setTimeout(r, 5)); }
  throw new Error('condition did not arrive');
};
function fixture() {
  const link = { session: 'session', state: { inventory: {} }, body: { current: null, pending: null, blocked: false },
    events: [], playing: () => true, changed() {}, notice(e) { this.events.push(e); }, calls: [],
    async plan() { return { steps: [{ kind: 'craft', item: 'stone_pickaxe', count: 1 }], inventory: { ...this.state.inventory } }; },
    async runSkill(skill, args) { this.calls.push([skill, args]); this.state.inventory.stone_pickaxe = 1; return { ok: true, note: {goal:{item:'stone_pickaxe'},target:1,inventory:{stone_pickaxe:1},returned:true} }; },
    stop() { this.body.current = null; } };
  const work = new GameTasks(link, { stopMs: 30 });
  return { link, work };
}

test('natural goal is handed off once without recipe planning; conflicts are rejected', async()=>{
  const {link,work}=fixture();link.plan=()=>assert.fail('Mindcraft owns planning');
  const a=work.submit(request());assert.equal(work.submit(request()).task_id,a.task_id);
  assert.equal(work.submit(request({arguments:{request:'Another goal'}})).reason,'request_id_conflict');
  await wait(()=>work.active.state==='succeeded');
  assert.equal(link.calls.length,1);assert.equal(link.calls[0][0],'pursue');
  assert.equal(link.calls[0][1].request,'Make a stone pickaxe');
  assert.equal(work.view().evidence.inventory.stone_pickaxe,1);work.close();
});

test('old structured requests and malformed natural requests are rejected',()=>{
  const {work}=fixture();
  for(const change of [{capability:'minecraft.obtain_item'}, {arguments:{request:''}},
    {arguments:{request:'x'.repeat(2001)}}, {arguments:{request:'a',item:'stone'}}, {constraints:{resource_scope:'search'}}])
    assert.equal(work.submit(request(change)).reason,'invalid_request');
  work.close();
});

test('success needs inventory, return and physical idle evidence',async()=>{
  for(const note of [{}, {goal:{item:'stone_pickaxe'},target:1,inventory:{},returned:true},
    {goal:{item:'stone_pickaxe'},target:1,inventory:{stone_pickaxe:1},returned:false}]) {
    const {link,work}=fixture();link.runSkill=async()=>({ok:true,note});work.submit(request());
    await wait(()=>work.active.state==='needs_decision');assert.equal(work.active.reason,'objective_unverified');work.close();
  }
});

test('runtime errors are surfaced without an outer recipe repair loop',async()=>{
  const {link,work}=fixture();link.runSkill=async()=>({ok:false,reason:'execution_error',note:{action:'collectBlocks'}});
  work.submit(request());await wait(()=>work.active.state==='needs_decision');
  assert.equal(work.view().reason,'execution_error');
  assert.equal((await work.answer(work.active.id,'stale','retry')).reason,'stale_decision');
  const deadline=work.active.deadline,id=work.active.id;
  await work.answer(id,work.active.decision.decision_id,'retry');await wait(()=>work.active.state==='needs_decision');
  assert.equal(work.active.deadline,deadline);assert.equal(work.active.id,id);work.close();
});

test('follow stops before handing a goal to Mindcraft; pending or blocked bodies refuse work',async()=>{
  const {link,work}=fixture();work.stopMs=1000;link.body.current={id:42,skill:'follow',phase:'running'};
  link.stop=id=>assert.equal(id,42);work.submit(request());
  await new Promise(r=>setTimeout(r,10));assert.equal(link.calls.length,0);
  link.body.current=null;await wait(()=>work.active.state==='succeeded');work.close();
  for(const patch of [{blocked:true},{pending:{id:2}},{owner:'defending'},{current:{id:1,skill:'pursue'}}]) {
    const f=fixture();Object.assign(f.link.body,patch);assert.equal(f.work.submit(request()).status,'busy');f.work.close();
  }
});

test('stop suppresses late success and holds ownership until physical idle',async()=>{
  const {link,work}=fixture();let release;
  link.runSkill=()=>new Promise(r=>{release=r;});work.submit(request());await wait(()=>release);
  link.body.blocked=true;assert.equal((await work.cancel(work.active.id)).reason,'stop_unconfirmed');
  assert.equal(work.submit(request({request_id:'other'})).status,'busy');
  link.body.blocked=false;assert.equal((await work.cancel(work.active.id)).state,'cancelled');
  release({ok:true,note:{goal:{item:'stone_pickaxe'},target:1,inventory:{stone_pickaxe:1},returned:true}});
  await new Promise(r=>setImmediate(r));assert.equal(work.active.state,'cancelled');work.close();
});

test('deadline stops work and explicit shortage policy remains a confirmed stop',async()=>{
  const f=fixture();f.link.runSkill=()=>new Promise(()=>{});f.work.submit(request({budget_ms:100}));
  await wait(()=>f.work.active.state==='failed');assert.equal(f.work.active.reason,'deadline');f.work.close();
  const {link,work}=fixture();link.runSkill=async()=>({ok:false,reason:'not_found',note:{goal:{item:'stone_pickaxe',failure_policy:'stop'}}});
  work.submit(request());await wait(()=>work.active.state==='cancelled');assert.equal(work.active.reason,'not_found');work.close();
});

test('activity updates match the running operation and cannot revive terminal work',async()=>{
  const {link,work}=fixture();link.runSkill=()=>new Promise(()=>{});work.submit(request());await wait(()=>work.active.operation);
  work.activity({request_id:'old',stage:'thinking'});assert.equal(work.active.evidence.activity,undefined);
  work.activity({request_id:work.active.operation,stage:'executing',command:'!collectBlocks'});
  assert.equal(work.active.evidence.activity.command,'!collectBlocks');
  await work.cancel(work.active.id);const rev=work.active.revision;
  work.activity({request_id:work.active.operation,stage:'thinking'});assert.equal(work.active.revision,rev);work.close();
});

test('construction validates plan before replacing follow', async () => {
  const { link, work } = fixture();
  link.body.current = { id: 42, skill: 'follow' };
  let stops = 0;
  link.stop = id => { assert.equal(id, 42); stops++; link.body.current = null; };
  const r = request({ capability: 'minecraft.edit_region', arguments: { plan_id: '11111111-1111-4111-8111-111111111111' }, constraints: { failure_policy: 'stop' } });
  link.claimRegion = () => ({ error: 'expired_plan' });
  assert.equal(work.submit(r).reason, 'expired_plan');
  assert.equal(stops, 0);
  link.claimRegion = () => ({ plan: { spec: {}, total: 1, actions: [1] } });
  link.runSkill = async () => ({ ok: true, note: { completed: true, total: 1, verified: 1, changed: 1 } });
  work.submit(r);
  await wait(() => work.active.state === 'succeeded');
  assert.equal(stops, 1);
  work.close();
});
test('prepared construction verifies physical evidence and deduplicates work',async()=>{
  const {link,work}=fixture(),plan_id='11111111-1111-4111-8111-111111111111';
  let claimed=false;
  link.claimRegion=()=>claimed?{error:'plan_already_used'}:(claimed=true,{plan:{spec:{},summary:'指定した床',total:9,actions:[1,2]}});
  link.runSkill=async(skill,args)=>{link.calls.push([skill,args]);return{ok:true,note:{completed:true,total:9,verified:9,changed:2,summary:'指定した床'}};};
  const r=request({capability:'minecraft.edit_region',arguments:{plan_id},constraints:{failure_policy:'stop'}});
  const a=work.submit(r);assert.equal(work.submit(r).task_id,a.task_id);
  await wait(()=>work.active.state==='succeeded');
  assert.equal(link.calls[0][0],'edit_region');assert.match(work.view().message,/2マス変更/);
  assert.equal(work.submit({...r,request_id:'two'}).reason,'plan_already_used');work.close();
});
test('construction ok without verified completion is stopped, never succeeded',async()=>{
  const {link,work}=fixture();
  link.claimRegion=()=>({plan:{spec:{},summary:'壁',total:9,actions:[1]}});
  link.runSkill=async()=>({ok:true,note:{changed:1}});
  work.submit(request({capability:'minecraft.edit_region',arguments:{plan_id:'11111111-1111-4111-8111-111111111111'},constraints:{failure_policy:'stop'}}));
  await wait(()=>work.active.state==='cancelled');assert.equal(work.view().reason,'objective_unverified');work.close();
});
