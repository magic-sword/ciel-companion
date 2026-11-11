import test from 'node:test';
import assert from 'node:assert/strict';
import { regionArgs, cells, regionStances } from '../src/spatial.js';
const a={x1:4,y1:64,z1:0,x2:6,y2:65,z2:1};
test('clearing stands on retained support and within reach',async()=>{
  const { Vec3 }=await import('vec3');
  const bot={entity:{position:new Vec3(4.5,65,.5)},blockAt:p=>({name:p.y<64?'dirt':'air',boundingBox:p.y<64?'block':'empty'})};
  const stances=regionStances(bot,a,new Vec3(4,64,0));
  assert.ok(stances.length);
  assert.ok(stances.every(p=>!cells(a,false).some(q=>q.equals(p.offset(0,-1,0)))));
  assert.ok(stances.every(p=>p.y===64));
});
test('region bounds reject oversized, reversed, noninteger and unsupported blocks',()=>{
  assert.equal(regionArgs(a).args.x1,4);
  for(const change of [{x2:100},{x1:7},{y1:1.5},{y1:-65},{x1:NaN}]) assert.equal(regionArgs({...a,...change}).error,'bad_args');
  assert.equal(regionArgs({...a,block:'tnt'},true).error,'bad_args');
  assert.equal(cells(a,false)[0].y,65);
  assert.equal(cells(a,true)[0].y,64);
});
