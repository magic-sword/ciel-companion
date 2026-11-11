import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Pointing,selectedRegion,actOnSelection } from '../src/pointing.js';
import { Vec3 } from 'vec3';
const id='11111111-1111-4111-8111-111111111111';
const other='22222222-2222-4222-8222-222222222222';
const point={x:5,y:63,z:0,block:'grass_block',face:[0,1,0]};
function fixture(t) {
  const folder=mkdtempSync(join(tmpdir(),'ciel-pointing-'));
  t.after(()=>rmSync(folder,{recursive:true,force:true}));
  const path=join(folder,'selection.json');
  const s={id,owner:'Owner',player_uuid:id,world:id,dimension:'overworld',created_at:1000,expires_at:61000,points:[point]};
  const write=(selections,extra={})=>writeFileSync(path,JSON.stringify({version:1,session:id,selections,...extra}));
  const bot={entity:{position:new Vec3(0,64,0)},game:{dimension:'overworld'}};
  const store=new Pointing(path,'Owner',()=>2000);
  write([s]); return {store,bot,s,write};
}
test('pointer selection is bounded by expiry, owner, dimension and validated geometry',t=>{
  const {store,bot,s,write}=fixture(t);
  assert.equal(store.latest(bot).selection_id,id);
  for(const patch of [{owner:'SomeoneElse'},{dimension:'the_nether'},{expires_at:1999},{created_at:3000},
    {points:[{...point,face:[1,1,0]}]},{points:[{...point,y:999}]}]) {
    write([{...s,...patch}]); assert.equal(store.latest(bot),null);
  }
});
test('new selection does not change an existing reference; invalidation removes both',t=>{
  const {store,bot,s,write}=fixture(t);
  write([s,{...s,id:other,points:[{...point,x:12}]}]);
  assert.equal(store.latest(bot).selection_id,other);
  assert.equal(store.resolve(bot,id).points[0].x,5);
  write([]); assert.equal(store.resolve(bot,id),null);
});
test('captured gaze survives looking away but not logout or a new server session',t=>{
  const {store,bot,s,write}=fixture(t);
  const live={gaze:{...s,expires_at:2500},published_at:2000,presence:{world:id,player_uuid:id}};
  write([],live);
  assert.equal(store.latest(bot).source,'owner_gaze');
  write([],{...live,gaze:{...s,id:other,points:[{...point,x:20}]}});
  store.latest(bot);
  assert.equal(store.resolve(bot,id).points[0].x,5);
  write([],{...live,gaze:null});
  assert.equal(store.resolve(bot,id).points[0].x,5);
  write([],{...live,presence:null});
  assert.equal(store.resolve(bot,id),null);
  write([],{...live,session:other});
  assert.equal(store.resolve(bot,id),null);
});
test('two selected corners preserve all axes and floor is above the surface',()=>{
  const s={points:[point,{...point,x:7,z:2}]};
  assert.deepEqual(selectedRegion(s,true,'oak_planks').args,{x1:5,y1:64,z1:0,x2:7,y2:64,z2:2,block:'oak_planks'});
  assert.equal(selectedRegion({points:[point]},false).error,'selection_needs_two_points');
  assert.equal(selectedRegion({points:[point,{...point,y:64}]},true,'oak_planks').error,'selection_floor_not_level');
  assert.equal(selectedRegion({points:[point,{...point,x:30,z:30}]},false).error,'bad_args');
});
test('changed block or missing selection cannot start movement or digging',async t=>{
  const {store,bot,s,write}=fixture(t);
  bot.pointing=store; bot.blockAt=()=>({name:'crafting_table'});
  const ctx={Failed:Error};
  await assert.rejects(actOnSelection(bot,{selection_id:id,action:'clear'},{},ctx),/selection_changed/);
  write([]);
  await assert.rejects(actOnSelection(bot,{selection_id:id,action:'recover'},{},ctx),/selection_expired/);
});
