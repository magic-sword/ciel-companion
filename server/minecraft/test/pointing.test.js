import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Pointing, placeNote } from '../src/pointing.js';
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
test('the newest selection wins, and the gaze is used only while it is fresh',t=>{
  const {store,bot,s,write}=fixture(t);
  write([s,{...s,id:other,points:[{...point,x:12}]}]);
  assert.equal(store.latest(bot).selection_id,other);
  const live={gaze:{...s,expires_at:2500},published_at:2000,presence:{world:id,player_uuid:id}};
  write([],live);
  assert.equal(store.latest(bot).source,'owner_gaze');
  write([],{...live,published_at:0});
  assert.equal(store.latest(bot),null);
});
test('a work resolves what the conversation was given, after the owner looks away, until it expires',t=>{
  let now=2000;
  const {store,bot,s,write}=fixture(t);
  store.now=()=>now;
  write([],{gaze:{...s,expires_at:2500},published_at:2000,presence:{world:id,player_uuid:id}});
  const given=store.latest(bot);
  write([]);   // looked away
  assert.deepEqual(store.place(bot,given.selection_id).points,[point]);
  assert.equal(store.place(bot,other),null);
  assert.equal(store.place(bot,'not-an-id'),null);
  write([{...s,id:other}]);
  assert.equal(store.place(bot,other).source,'owner_pointer');
  now=70000;
  assert.equal(store.place(bot,given.selection_id),null);
});
test('the place note names the block, or the range by axis',()=>{
  assert.match(placeNote({points:[point],source:'owner_gaze'}),/見ていた.*x=5, y=63, z=0（grass_block）/);
  const range=placeNote({points:[point,{...point,x:9,z:-2,block:'stone'}],source:'owner_pointer'});
  assert.match(range,/x=5〜9, y=63, z=-2〜0/); assert.match(range,/grass_block と stone/);
});
