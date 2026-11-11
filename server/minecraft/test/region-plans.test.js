import test from 'node:test';
import assert from 'node:assert/strict';
import minecraftData from 'minecraft-data';
import {Vec3} from 'vec3';
import {normalizeRegionSpec,compileRegion,executeRegion,RegionPlans} from '../src/spatial.js';
const region={x1:4,x2:6,y1:64,y2:64,z1:0,z2:2};
const spec=(operation='floor',extra={})=>normalizeRegionSpec({operation,region,...(operation==='clear'?{clear_blocks:['dirt']}:{block:'oak_planks'}),on_protected:'stop_before_edit',...extra});
const k=p=>`${p.x},${p.y},${p.z}`;
test('pointed leveling derives bounds in game and validates heights',()=>{
  const input={operation:'level',selection_id:'opaque',level:{ground_y:63,top_y:65},clear_blocks:['dirt'],on_protected:'stop_before_edit'};
  assert.equal(normalizeRegionSpec(input,{points:[{x:4,y:61,z:0},{x:6,y:67,z:1}]}).region.y1,64);
  assert.throws(()=>normalizeRegionSpec(input),/selection_needs_two_points/);
  assert.throws(()=>normalizeRegionSpec({...input,level:{ground_y:65,top_y:63}},{points:[{x:4,y:61,z:0},{x:6,y:67,z:1}]}),/invalid_level/);
});
function fixture() {
  const blocks=new Map(),effects=[],inventory={oak_planks:64,dirt:64,cobblestone:64,stone:64,glass:64};
  const bot={registry:minecraftData('1.21.11'),game:{dimension:'overworld'},entity:{position:new Vec3(.5,64,.5)},
    inventory:{items:()=>Object.entries(inventory).filter(([,count])=>count).map(([name,count])=>({name,count}))},
    blockAt(p){const name=blocks.get(k(p))??(p.y<64?'stone':'air');return{name,stateId:bot.registry.blocksByName[name]?.minStateId,
      boundingBox:name==='air'?'empty':'block',position:p.clone(),diggable:true};},
    pathfinder:{setMovements(){},async goto(goal){effects.push('move');bot.entity.position=new Vec3(goal.x+.5,goal.y,goal.z+.5);}},
    async equip(item){effects.push('equip');bot.hand=item.name;},
    async placeBlock(reference,face){effects.push('place');blocks.set(k(reference.position.plus(face)),bot.hand);inventory[bot.hand]--;},
    async dig(b){effects.push('dig');blocks.set(k(b.position),'air');},async waitForTicks(){}};
  return {bot,blocks,effects,inventory,ctx:{Failed:Error,watched:async(_,f)=>f()}};
}
test('planning is read only; 64-cell floor is reachable and has an exit',async()=>{
  const {bot,effects}=fixture();
  const p=compileRegion(bot,spec('floor',{region:{...region,x2:11,z2:7}}));
  assert.equal(p.actions.length,64);assert.deepEqual(effects,[]);
  assert.ok(p.actions.every(a=>k(a.p)!==k(a.stance)));
});
test('partial floor and both wall orientations consume only missing cells',async()=>{
  for(const r of [region,{...region,y2:66,z2:0},{...region,x2:4,y2:66}]) {
    const {bot,blocks,ctx,inventory}=fixture();blocks.set('4,64,0','oak_planks');
    const p=compileRegion(bot,spec(r.y2===64?'floor':'wall',{region:r}));
    const before=inventory.oak_planks,result=await executeRegion(bot,p,{},ctx,10000);
    assert.equal(result.completed,true);assert.equal(result.changed,8);assert.equal(before-inventory.oak_planks,8);
  }
});
test('backfill fills irregular deep holes without replacing retained stone',async()=>{
  const {bot,blocks,ctx}=fixture();
  for(let x=4;x<=6;x++)for(let y=61;y<=63;y++)for(let z=0;z<=1;z++)blocks.set(`${x},${y},${z}`,'air');
  blocks.set('5,61,0','stone');
  const p=compileRegion(bot,spec('backfill',{region:{...region,y1:61,y2:63,z2:1},block:'dirt'}));
  assert.equal(p.actions.length,17);
  const done=await executeRegion(bot,p,{},ctx,10000);
  assert.equal(done.completed,true);assert.equal(blocks.get('5,61,0'),'stone');
});
test('known shortage, protected blocks, overlap and unsupported hazards never edit',()=>{
  const cases=[
    f=>{f.inventory.oak_planks=8;return [spec(),'missing_materials'];},
    f=>{f.blocks.set('5,64,1','chest');return [spec('clear'),'protected_block'];},
    f=>{f.blocks.set('7,64,1','sand');return [spec(),'hazard_near_region'];},
    f=>{f.blocks.set('5,64,1','stone');return [spec(),'occupied_region'];},
  ];
  for(const setup of cases){const f=fixture();const[s,reason]=setup(f);assert.throws(()=>compileRegion(f.bot,s),new RegExp(reason));assert.deepEqual(f.effects,[]);}
  assert.throws(()=>spec('clear',{preserve_regions:[region]}),/protected_overlap/);
});

test('a required harvest tool is checked before any partial clearing',()=>{
  const {bot,blocks,inventory,effects}=fixture();blocks.set('4,64,0','dirt');blocks.set('5,64,0','stone');
  const input=spec('clear',{clear_blocks:['dirt','stone'],region:{...region,x2:5,z2:0}});
  assert.throws(()=>compileRegion(bot,input),/needs_tool/);assert.deepEqual(effects,[]);
  inventory.iron_pickaxe=1;assert.equal(compileRegion(bot,input).actions.length,2);
});
test('64/65 cells, unsupported material, plane and height boundaries',()=>{
  assert.throws(()=>spec('floor',{region:{...region,x2:68,z2:0}}),/bad_args/);
  assert.throws(()=>spec('floor',{block:'tnt'}),/unsupported_material/);
  assert.throws(()=>spec('wall'),/wall_not_plane/);
  assert.throws(()=>spec('floor',{region:{...region,y2:65}}),/floor_not_level/);
  assert.throws(()=>spec('clear',{clear_blocks:['sand']}),/unsupported_material/);
  assert.throws(()=>spec('floor',{expected_dimensions:[2,2]}),/dimension_mismatch/);
  assert.doesNotThrow(()=>spec('floor',{expected_dimensions:[3,3]}));
  const s=normalizeRegionSpec({operation:'level',level:{x1:4,x2:6,z1:0,z2:1,ground_y:63,top_y:65},clear_blocks:['dirt'],on_protected:'stop_before_edit'});
  assert.equal(s.region.y1,64);assert.equal(s.region.y2,65);
});
test('plans are scoped, expiring, idempotent, bounded and consumed once',()=>{
  const f=fixture();let now=0;
  const store=new RegionPlans({clock:()=>now}),r={request_id:'one',draft_revision:1,spec:spec()};
  const a=store.prepare(f.bot,r,'session');assert.equal(a.status,'ready');
  assert.equal(store.prepare(f.bot,r,'session').plan_id,a.plan_id);
  assert.equal(store.prepare(f.bot,{...r,spec:spec('floor',{block:'glass'})},'session').reason,'request_id_conflict');
  assert.equal(store.claim(a.plan_id,'other','t').error,'unknown_plan');
  assert.ok(store.claim(a.plan_id,'session','t').plan);
  assert.equal(store.claim(a.plan_id,'session','t2').error,'plan_already_used');
  store.start(f.bot,a.plan_id,'session');assert.throws(()=>store.start(f.bot,a.plan_id,'session'),/unknown_plan/);
  const b=store.prepare(f.bot,{...r,request_id:'two'},'session');now=60000;
  assert.equal(store.claim(b.plan_id,'session','t').error,'plan_expired');
  store.clear('session');assert.equal(store.plans.size,0);
});
test('changed world after preparation and during equip cannot be overwritten',async()=>{
  for(const moment of ['before','equip']) {
    const f=fixture(),p=compileRegion(f.bot,spec());
    if(moment==='before')f.blocks.set('5,64,1','chest');
    else f.bot.equip=async()=>{f.blocks.set('5,64,1','chest');};
    await assert.rejects(executeRegion(f.bot,p,{},f.ctx,10000),/region_changed/);
    assert.ok(!f.effects.includes('place'));assert.equal(f.blocks.get('5,64,1'),'chest');
  }
});
test('cancel during equip or tool selection permits no subsequent edit',async()=>{
  for(const operation of ['floor','clear']) {
    const f=fixture(),token={cancelled:false};
    if(operation==='clear')for(let x=4;x<=6;x++)for(let z=0;z<=2;z++)f.blocks.set(`${x},64,${z}`,'dirt');
    const p=compileRegion(f.bot,spec(operation));
    f.bot.equip=async()=>{token.cancelled=true;};
    f.bot.tool={equipForBlock:async()=>{token.cancelled=true;}};
    const done=await executeRegion(f.bot,p,token,f.ctx,10000);
    assert.equal(done.changed,0);assert.ok(!f.effects.includes('place'));assert.ok(!f.effects.includes('dig'));
  }
});
test('already complete verifies without movement or material use',async()=>{
  const f=fixture();for(let x=4;x<=6;x++)for(let z=0;z<=2;z++)f.blocks.set(`${x},64,${z}`,'oak_planks');
  f.inventory.oak_planks=0;
  const p=compileRegion(f.bot,spec()),done=await executeRegion(f.bot,p,{},f.ctx,10000);
  assert.equal(done.completed,true);assert.equal(done.changed,0);assert.deepEqual(f.effects,[]);
});

test('a transient path prediction failure replans once and cancellation during settling never edits',async()=>{
  for(const cancel of [false,true]){
    const f=fixture(),token={cancelled:false},p=compileRegion(f.bot,spec());
    f.bot.entity.onGround=true;
    const original=f.bot.pathfinder.goto;let calls=0;
    f.bot.pathfinder.goto=async goal=>{if(++calls===1)throw new Error('No path');return original(goal);};
    f.bot.pathfinder.setGoal=()=>{};
    f.bot.waitForTicks=async()=>{if(cancel)token.cancelled=true;};
    const done=await executeRegion(f.bot,p,token,f.ctx,10000);
    if(cancel){assert.equal(calls,1);assert.equal(done.changed,0);assert.ok(!f.effects.includes('place'));}
    else{assert.equal(done.completed,true);assert.equal(done.path_repairs,1);}
  }
});

test('a blocked diagonal uses an observed safe adjacent waypoint without editing it',async()=>{
  const f=fixture(),p=compileRegion(f.bot,spec()),destination=p.actions[0].stance;
  f.bot.entity.position=destination.offset(-.5,0,-.5);f.bot.entity.onGround=true;
  f.bot.pathfinder.setGoal=()=>{};
  const original=f.bot.pathfinder.goto,calls=[];
  f.bot.pathfinder.goto=async goal=>{
    calls.push([goal.x,goal.y,goal.z]);
    if(calls.length<=2)throw new Error('No path');
    return original(goal);
  };
  const done=await executeRegion(f.bot,p,{},f.ctx,10000);
  assert.equal(done.completed,true);assert.equal(done.path_repairs,2);
  assert.notDeepEqual(calls[2],calls[0]);assert.deepEqual(calls[3],calls[0]);
  assert.equal(f.effects.filter(v=>v==='place').length,p.actions.length);
});
