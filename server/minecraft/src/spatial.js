// Finite construction plans. World reads and survival actions only; no commands.
import { randomUUID, createHash } from 'node:crypto';
import { Vec3 } from 'vec3';
import pathfinderPkg from 'mineflayer-pathfinder';
import { carefulMovements } from './movements.js';
import {shortWhy} from './ciel/words.js';
const { goals } = pathfinderPkg;
export const BUILD_BLOCKS = ['dirt', 'cobblestone', 'stone', 'oak_planks', 'glass'];
export const CLEAR_BLOCKS = ['dirt', 'grass_block', 'stone', 'cobblestone'];
const FIELDS = ['x1', 'y1', 'z1', 'x2', 'y2', 'z2'];
const AIR = new Set(['air', 'cave_air', 'void_air']);
const HAZARD = /water|lava|sand$|gravel|concrete_powder|anvil|piston|redstone|tripwire|torch|rail|ladder|scaffolding|carpet|snow$|vine|leaves|door|trapdoor|button|lever|pressure_plate|tall_grass|flower/;
const key = p => `${p.x},${p.y},${p.z}`;
const position = k => new Vec3(...k.split(',').map(Number));
const air = b => AIR.has(b.name);
const state = b => `${b.name}:${b.stateId ?? ''}`;
const plain = v => v && typeof v === 'object' && !Array.isArray(v);
const only = (v, keys) => plain(v) && Object.keys(v).every(k => keys.includes(k));
const error = (reason, note = {}) => Object.assign(new Error(reason), { reason, note });
export function regionArgs(a, build = false) {
  if (!a || FIELDS.some(k => !Number.isSafeInteger(a[k]) || Math.abs(a[k]) > 29999984)
      || a.y1 < -64 || a.y2 > 319 || a.x1 > a.x2 || a.y1 > a.y2 || a.z1 > a.z2
      || (a.x2-a.x1+1)*(a.y2-a.y1+1)*(a.z2-a.z1+1) > 64
      || (build && !BUILD_BLOCKS.includes(a.block))) return { error: 'bad_args' };
  return { args: Object.fromEntries([...FIELDS, ...(build ? ['block'] : [])].map(k => [k, a[k]])) };
}
export function cells(a, build) {
  const out = [];
  for (let y=a.y1; y<=a.y2; y++) for (let x=a.x1; x<=a.x2; x++) for (let z=a.z1; z<=a.z2; z++) out.push(new Vec3(x,y,z));
  return out.sort((p,q) => build ? p.y-q.y : q.y-p.y);
}

export function normalizeRegionSpec(spec, selection = null) {
  if (!only(spec, ['operation','region','selection_id','level','block','clear_blocks','preserve_regions','on_protected','expected_dimensions'])
      || !['clear','level','floor','wall','backfill'].includes(spec.operation)
      || spec.on_protected !== 'stop_before_edit') throw error('invalid_spec');
  const build = !['clear','level'].includes(spec.operation);
  if (build && !BUILD_BLOCKS.includes(spec.block)) throw error('unsupported_material');
  const targets = ['region','selection_id','level'].filter(k => spec[k] !== undefined);
  const pointedLevel=spec.operation==='level'&&spec.selection_id!==undefined&&spec.level!==undefined&&spec.region===undefined;
  if (targets.length !== 1 && !pointedLevel) throw error('ambiguous_region');
  let region;
  if (spec.selection_id !== undefined) {
    if (!selection || selection.points.length !== 2) throw error('selection_needs_two_points');
    const [a,b] = selection.points;
    if (spec.operation === 'floor' && (a.y !== b.y || a.face?.[1] !== 1 || b.face?.[1] !== 1)) throw error('selection_floor_not_level');
    region = Object.fromEntries(['x','y','z'].flatMap(k => [[k+'1',Math.min(a[k],b[k])],[k+'2',Math.max(a[k],b[k])]]));
    if (spec.operation === 'floor') { region.y1++; region.y2++; }
    if(pointedLevel) {
      const heights=spec.level;
      if(!only(heights,['ground_y','top_y'])||!Number.isSafeInteger(heights.ground_y)||!Number.isSafeInteger(heights.top_y)
          ||heights.ground_y>=heights.top_y)throw error('invalid_level');
      region.y1=heights.ground_y+1;region.y2=heights.top_y;
    }
  } else if (spec.level !== undefined) {
    const a=spec.level;
    if (spec.operation !== 'level' || !only(a,['x1','x2','z1','z2','ground_y','top_y'])
        || Object.values(a).some(n=>!Number.isSafeInteger(n)) || a.ground_y >= a.top_y) throw error('invalid_level');
    region={x1:a.x1,x2:a.x2,z1:a.z1,z2:a.z2,y1:a.ground_y+1,y2:a.top_y};
  } else region=spec.region;
  if (!only(region,FIELDS) || regionArgs(region).error) throw error('bad_args');
  if (spec.operation === 'floor' && region.y1 !== region.y2) throw error('floor_not_level');
  if (spec.operation === 'wall' && (region.y1 === region.y2 || (region.x1 !== region.x2 && region.z1 !== region.z2))) throw error('wall_not_plane');
  if(spec.expected_dimensions!==undefined) {
    const d=spec.expected_dimensions,sizes=['x','y','z'].map(k=>region[k+'2']-region[k+'1']+1);
    const expected=d?.length===3?sizes:['floor','level'].includes(spec.operation)?[sizes[0],sizes[2]]:
      spec.operation==='wall'?[Math.max(sizes[0],sizes[2]),sizes[1]]:[];
    if(!Array.isArray(d)||![2,3].includes(d.length)||d.some(n=>!Number.isSafeInteger(n)||n<1||n>64)
        ||expected.length!==d.length||d.some((n,i)=>n!==expected[i]))throw error('dimension_mismatch');
  }
  const preserve = spec.preserve_regions ?? [];
  if (!Array.isArray(preserve) || preserve.length > 4 || preserve.some(a=>!only(a,FIELDS)||regionArgs(a).error)) throw error('invalid_preserve_region');
  const clear=spec.clear_blocks ?? CLEAR_BLOCKS;
  if(!build && !spec.clear_blocks)throw error('material_required');
  if (!Array.isArray(clear) || !clear.length || clear.some(n=>!CLEAR_BLOCKS.includes(n)) || new Set(clear).size!==clear.length) throw error('unsupported_material');
  const edit = new Set(cells(region,build).map(key));
  if (preserve.some(a=>cells(a,false).some(p=>edit.has(key(p))))) throw error('protected_overlap');
  return { operation:spec.operation,region:{...region},...(build?{block:spec.block}:{}),clear_blocks:clear,
    ...(spec.expected_dimensions?{expected_dimensions:[...spec.expected_dimensions]}:{}),
    preserve_regions:structuredClone(preserve),on_protected:'stop_before_edit' };
}

export function regionStances(bot, a, target, read = p => bot.blockAt(p), forbidden = new Set(cells(a,false).map(key))) {
  const out=[];
  for(let x=target.x-2;x<=target.x+2;x++) for(let z=target.z-2;z<=target.z+2;z++)
    for(let y=target.y-4;y<=target.y+3;y++) {
      const p=new Vec3(x,y,z),foot=read(p),head=read(p.offset(0,1,0)),floor=read(p.offset(0,-1,0));
      if(foot && head && floor && air(foot) && air(head) && floor.boundingBox==='block'
          && !forbidden.has(key(p.offset(0,-1,0))) && key(p)!==key(target) && key(p.offset(0,1,0))!==key(target)
          && p.offset(.5,1.62,.5).distanceTo(target.offset(.5,.5,.5))<4.3) out.push(p);
    }
  return out.sort((p,q)=>p.distanceTo(bot.entity.position)-q.distanceTo(bot.entity.position));
}

function reachable(read, start, limits) {
  const inside=p=>p.x>=limits.x1&&p.x<=limits.x2&&p.y>=limits.y1&&p.y<=limits.y2&&p.z>=limits.z1&&p.z<=limits.z2;
  const walk=p=>inside(p)&&air(read(p))&&air(read(p.offset(0,1,0)))&&read(p.offset(0,-1,0)).boundingBox==='block';
  const found=new Set(),queue=[start];found.add(key(start));
  for(let i=0;i<queue.length;i++) {
    const p=queue[i];
    for(const[x,z]of [[1,0],[-1,0],[0,1],[0,-1],])for(const y of [0,1,-1,-2,-3]) {
      const q=p.offset(x,y,z),k=key(q);
      const descentClear=y>=0||Array.from({length:-y},(_,i)=>air(read(q.offset(0,2+i,0)))).every(Boolean);
      if(!found.has(k)&&walk(q)&&(y!==1||air(read(p.offset(0,2,0))))&&descentClear) {
        found.add(k);queue.push(q);
      }
    }
  }
  return found;
}

function visible(read,stance,destination,allowed) {
  const eye=stance.offset(.5,1.62,.5),direction=destination.minus(eye),length=direction.norm();
  for(let d=.1;d<length;d+=.1) {
    const p=eye.plus(direction.scaled(d/length)).floored(),b=read(p);
    if(b.boundingBox==='block'&&key(p)!==allowed)return false;
  }
  return true;
}

export function compileRegion(bot, spec) {
  const {region:a}=spec,build=!['clear','level'].includes(spec.operation);
  const positions=cells(a,build),start=bot.entity.position.floored();
  if(positions.some(p=>p.distanceTo(bot.entity.position)>32))throw error('region_too_far');
  const bounds={x1:Math.min(a.x1-2,start.x-1),x2:Math.max(a.x2+2,start.x+1),
    y1:Math.max(-64,Math.min(a.y1-3,start.y-2)),y2:Math.min(319,Math.max(a.y2+3,start.y+2)),
    z1:Math.min(a.z1-2,start.z-1),z2:Math.max(a.z2+2,start.z+1)};
  const snapshot=new Map();
  const capture=p=>{
    const k=key(p);if(snapshot.has(k))return snapshot.get(k);
    if(snapshot.size>=4096)throw error('observation_limit');
    const b=bot.blockAt(p);if(!b)throw error('unloaded_region');
    const value={name:b.name,stateId:b.stateId,boundingBox:b.boundingBox};snapshot.set(k,value);return value;
  };
  const expected=new Map(),changes=[];
  for(const p of positions) {
    const b=capture(p);
    if(!build&&!air(b)&&!spec.clear_blocks.includes(b.name))throw error('protected_block',{at:key(p)});
    if(build&&!air(b)&&b.name!==spec.block&&!(spec.operation==='backfill'&&CLEAR_BLOCKS.includes(b.name)))throw error('occupied_region',{at:key(p)});
    const name=build?(spec.operation==='backfill'&&!air(b)?b.name:spec.block):'air';
    expected.set(key(p),name);
    if(b.name!==name&&!(name==='air'&&air(b)))changes.push(p);
  }
  const count=()=>bot.inventory.items().filter(i=>i.name===spec.block).reduce((n,i)=>n+i.count,0);
  if(build&&count()<changes.length)throw error('missing_materials',{required:changes.length,available:count(),missing:changes.length-count()});
  for(const r of spec.preserve_regions)for(const p of cells(r,false))capture(p);
  const volume=(bounds.x2-bounds.x1+1)*(bounds.y2-bounds.y1+1)*(bounds.z2-bounds.z1+1);
  if(volume>4096)throw error('observation_limit');
  for(let x=bounds.x1;x<=bounds.x2;x++)for(let y=bounds.y1;y<=bounds.y2;y++)for(let z=bounds.z1;z<=bounds.z2;z++) {
    const p=new Vec3(x,y,z),b=capture(p);
    if(HAZARD.test(b.name)||b.name==='fire'||b.name==='tnt')throw error('hazard_near_region',{at:key(p),block:b.name});
  }
  const simulated=new Map(snapshot),read=p=>simulated.get(key(p))??{name:'unknown',boundingBox:'empty'};
  const forbidden=build?new Set():new Set(changes.map(key));
  let stance=start;
  const actions=[];
  changes.sort((p,q)=>(build?p.y-q.y:q.y-p.y)||q.distanceTo(start)-p.distanceTo(start));
  for(const p of changes) {
    const access=reachable(read,stance,bounds);
    const candidates=regionStances(bot,a,p,read,forbidden).filter(s=>access.has(key(s)));
    if(!candidates.length)throw error('unsafe_stance',{at:key(p)});
    candidates.sort((s,t)=>(spec.operation==='backfill'?
      Math.max(0,p.y+1-s.y)-Math.max(0,p.y+1-t.y):0)||s.distanceTo(stance)-t.distanceTo(stance));
    const faces=build?[new Vec3(0,1,0),new Vec3(1,0,0),new Vec3(-1,0,0),new Vec3(0,0,1),new Vec3(0,0,-1)].filter(f=>read(p.minus(f)).boundingBox==='block'):[null];
    if(!faces.length)throw error('no_support');
    let choice;
    for(const s of candidates) {
      const f=faces.find(f=>visible(read,s,build?p.offset(.5,.5,.5).minus(f.scaled(.499)):p.offset(.5,.5,.5),build?key(p.minus(f)):key(p)));
      if(f!==undefined){choice={stance:s,face:f};break;}
    }
    if(!choice)throw error('unsafe_stance',{at:key(p)});
    stance=choice.stance;const face=choice.face;
    if(!build) {
      const block=bot.blockAt(p);
      if(block?.diggable===false)throw error('cannot_harvest');
      const tools=block?.harvestTools??bot.registry?.blocksByName[block?.name]?.harvestTools;
      if(tools&&!bot.inventory.items().some(item=>tools[item.type??bot.registry?.itemsByName[item.name]?.id]))
        throw error('needs_tool',{at:key(p)});
    }
    actions.push({p,stance,face});
    simulated.set(key(p),{name:build?spec.block:'air',boundingBox:build?'block':'empty'});forbidden.delete(key(p));
  }
  const sizes=['x','y','z'].map(k=>a[k+'2']-a[k+'1']+1);
  const summary=`X=${a.x1}〜${a.x2}、Y=${a.y1}〜${a.y2}、Z=${a.z1}〜${a.z2}（${sizes.join('×')}、${positions.length}マス）。変更予定${actions.length}マス`;
  return {spec:structuredClone(spec),snapshot,expected,actions,total:positions.length,required:build?changes.length:0,
    initial_materials:build?count():0,summary,dimension:String(bot.game?.dimension??''),start:bot.entity.position.clone()};
}

export class RegionPlans {
  constructor({clock=()=>performance.now()}={}) {this.clock=clock;this.plans=new Map();this.requests=new Map();}
  prepare(bot,r,scope) {
    if(!only(r,['request_id','draft_revision','spec'])||typeof r.request_id!=='string'||!r.request_id||r.request_id.length>160
        ||!Number.isSafeInteger(r.draft_revision)||r.draft_revision<1||!bot?.entity||!scope)return {status:'refused',reason:'invalid_request'};
    const id=`${scope}:${r.request_id}:${r.draft_revision}`,signature=JSON.stringify(r.spec),known=this.requests.get(id);
    if(known)return known.signature===signature?structuredClone(known.result):{status:'refused',reason:'request_id_conflict'};
    for(const [key,value]of this.plans)if(value.expires<=this.clock())this.plans.delete(key);
    if(this.plans.size>=32)return {status:'refused',reason:'plan_limit'};
    try {
      const selected=r.spec?.selection_id?bot.pointing?.resolve(bot,r.spec.selection_id):null;
      if(r.spec?.selection_id&&!selected)throw error('selection_expired');
      if(selected&&selected.points.some(p=>bot.blockAt(new Vec3(p.x,p.y,p.z))?.name!==p.block))throw error('selection_changed');
      const plan=compileRegion(bot,normalizeRegionSpec(r.spec,selected)),plan_id=randomUUID();
      Object.assign(plan,{scope,expires:this.clock()+Math.min(60000,selected?selected.expires_at-Date.now():60000),task:null,started:false});
      this.plans.set(plan_id,plan);
      const result={status:'ready',plan_id,summary:plan.summary,total:plan.total,required:plan.required,
        spec:plan.spec,spec_hash:createHash('sha256').update(JSON.stringify(plan.spec)).digest('hex')};
      this.requests.set(id,{signature,result});return structuredClone(result);
    }catch(e){return {status:e.reason==='dimension_mismatch'?'needs_clarification':'refused',reason:e.reason??'preparation_error',evidence:e.note??{},
      message:e.reason==='dimension_mismatch'?'座標から計算した寸法と指定寸法が一致しません。最終の範囲と寸法を指定してください。':
        e.reason==='missing_materials'?`材料不足です。必要${e.note.required}個、所持${e.note.available}個、あと${e.note.missing}個です。`:
          `施工を開始していません。${shortWhy(e.reason,e.note)}。`};}
  }
  claim(id,scope,task) {
    const p=this.plans.get(id);
    if(!p||p.scope!==scope)return {error:'unknown_plan'};
    if(p.task)return {error:'plan_already_used'};
    if(this.clock()>=p.expires)return {error:'plan_expired'};
    p.task=task;return {plan:p};
  }
  start(bot,id,scope) {
    const p=this.plans.get(id);
    if(!p||p.scope!==scope||!p.task||p.started)throw error('unknown_plan');
    p.started=true;
    if(this.clock()>=p.expires||String(bot.game?.dimension??'')!==p.dimension)throw error('plan_expired');
    return p;
  }
  clear(scope) {
    for(const[id,p]of this.plans)if(p.scope===scope)this.plans.delete(id);
    for(const id of this.requests.keys())if(id.startsWith(scope+':'))this.requests.delete(id);
  }
}

export async function executeRegion(bot,plan,token,{guard,Failed,watched,move,dig,place},budgetMs) {
  const deadline=performance.now()+Math.min(120000,budgetMs),expectedStates=new Map(plan.snapshot);
  let changed=0,stepRepairs=0,pathRepairs=0;
  const note=()=>({changed,verified:plan.total-plan.actions.length+changed,total:plan.total,step_repairs:stepRepairs,path_repairs:pathRepairs,remaining:plan.actions.slice(changed).map(a=>key(a.p)),summary:plan.summary});
  const fail=reason=>{const e=new Failed(reason);e.note=note();throw e;};
  const check=()=>{
    if(token.cancelled)return false;
    if(performance.now()>=deadline)fail('region_timeout');
    if(String(bot.game?.dimension??'')!==plan.dimension)fail('region_changed');
    for(const[k,expected]of expectedStates){const b=bot.blockAt(position(k));if(!b||state(b)!==state(expected))fail('region_changed');}
    return true;
  };
  if(!check())return note();
  const build=!['clear','level'].includes(plan.spec.operation);
  const inventory=()=>bot.inventory.items().filter(i=>i.name===plan.spec.block).reduce((n,i)=>n+i.count,0);
  const initialMaterials=build?inventory():0;
  if(build&&inventory()<plan.required)fail('missing_materials');
  for(const action of plan.actions) {
    if(!check())return note();
    await guard?.idle(token);if(!check())return note();
    bot.pathfinder.setMovements(carefulMovements(bot));
    const go=s=>move ? move(s) : watched(bot,()=>bot.pathfinder.goto(new goals.GoalBlock(s.x,s.y,s.z)),2000);
    try {await go(action.stance);}
    catch(e) {
      if(!check())return note();
      bot.pathfinder.setGoal(null);
      for(let tick=0;tick<20&&!bot.entity.onGround&&check();tick++)await bot.waitForTicks(1);
      if(!check())return note();
      // Placement can leave the player close to a new block's corner. Let the
      // body settle and replan the same safe destination before trying a step.
      let recovered=false;
      if(pathRepairs<3){
        pathRepairs++;
        await bot.waitForTicks(4);if(!check())return note();
        try {await go(action.stance);recovered=true;}
        catch(e){if(!check())return note();bot.pathfinder.setGoal(null);}
      }
      if(!recovered){
      for(let tick=0;tick<20&&!bot.entity.onGround&&check();tick++)await bot.waitForTicks(1);
      if(!check())return note();
      const here=bot.entity.position.floored();
      if(action.stance.y===here.y&&pathRepairs<3){
        const adjacent=[[1,0],[-1,0],[0,1],[0,-1]].map(([x,z])=>here.offset(x,0,z)).filter(p=>
          [p,p.offset(0,1,0),p.offset(0,-1,0)].every(q=>expectedStates.has(key(q)))
          &&air(bot.blockAt(p))&&air(bot.blockAt(p.offset(0,1,0)))&&bot.blockAt(p.offset(0,-1,0)).boundingBox==='block'
          &&p.distanceTo(action.stance)<here.distanceTo(action.stance)).sort((p,q)=>p.distanceTo(action.stance)-q.distanceTo(action.stance));
        if(adjacent.length){
          pathRepairs++;
          try {await go(adjacent[0]);if(!check())return note();await go(action.stance);recovered=true;}
          catch(e){if(!check())return note();bot.pathfinder.setGoal(null);}
        }
      }
      }
      if(!recovered){
      for(let tick=0;tick<20&&!bot.entity.onGround&&check();tick++)await bot.waitForTicks(1);
      if(!check())return note();
      // The pathfinder's physics prediction can refuse the first jump out of a
      // one-cell depression. Use one observed, bounded vertical step; never dig
      // or scaffold to escape. The original work deadline still applies.
      const here=bot.entity.position.floored(),read=p=>bot.blockAt(p);
      const candidates=[[1,0],[-1,0],[0,1],[0,-1]].map(([x,z])=>here.offset(x,1,z)).filter(p=>{
        if(!expectedStates.has(key(p))||!expectedStates.has(key(p.offset(0,1,0)))||!expectedStates.has(key(p.offset(0,-1,0))))return false;
        const foot=read(p),head=read(p.offset(0,1,0)),floor=read(p.offset(0,-1,0));
        return foot&&head&&floor&&air(foot)&&air(head)&&floor.boundingBox==='block';
      }).sort((p,q)=>p.distanceTo(action.stance)-q.distanceTo(action.stance));
      if(!bot.entity.onGround||action.stance.y<=here.y||!candidates.length||stepRepairs>=3||!air(read(here.offset(0,2,0)))||!air(read(here.offset(0,3,0)))) {
        const failure=new Failed('no_path');failure.note={...note(),target:key(action.p),stance:key(action.stance),
          on_ground:bot.entity.onGround,feet:key(here),up_steps:candidates.map(key)};throw failure;
      }
      stepRepairs++;
      bot.pathfinder.setGoal(null);
      bot.setControlState('jump',true);
      try {for(let tick=0;tick<6&&check();tick++)await bot.waitForTicks(1);}
      finally {bot.setControlState('jump',false);}
      if(!check())return note();
      try {await go(candidates[0]);if(check())await go(action.stance);}
      catch(e) {fail('no_path');}
      }
    }
    if(!check())return note();
    const {p,face}=action;
    if(Math.floor(bot.entity.position.x)===p.x&&Math.floor(bot.entity.position.z)===p.z&&p.y<=Math.floor(bot.entity.position.y)+1)fail('unsafe_stance');
    if(build) {
      const item=bot.inventory.items().find(i=>i.name===plan.spec.block);if(!item)fail('missing_materials');
      await bot.equip(item,'hand');if(!check())return note();
      if(place) await place(p,plan.spec.block); else await bot.placeBlock(bot.blockAt(p.minus(face)),face);
    }else{
      if(bot.tool?.equipForBlock)await bot.tool.equipForBlock(bot.blockAt(p),{});
      if(!check())return note();if(dig) await dig(p); else await bot.dig(bot.blockAt(p));
    }
    await bot.waitForTicks(2);
    const b=bot.blockAt(p),wanted=plan.expected.get(key(p));
    if(!b||(wanted==='air'?!air(b):b.name!==wanted))fail('objective_unverified');
    expectedStates.set(key(p),{name:b.name,stateId:b.stateId,boundingBox:b.boundingBox});changed++;
    if(!check())return note();
  }
  if(!check())return note();
  for(const[k,wanted]of plan.expected){const b=bot.blockAt(position(k));if(!b||(wanted==='air'?!air(b):b.name!==wanted))fail('objective_unverified');}
  const consumed=build?initialMaterials-inventory():0;
  if(build&&consumed!==changed)fail('material_consumption_mismatch');
  return {...note(),consumed,completed:true};
}
