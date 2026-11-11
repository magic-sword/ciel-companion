import { readFileSync, statSync } from 'node:fs';
import { Vec3 } from 'vec3';
import { regionArgs, editRegion } from './spatial.js';
import { carefulMovements } from './movements.js';
import pathfinderPkg from 'mineflayer-pathfinder';
const { goals } = pathfinderPkg;
const UUID = /^[a-f0-9-]{36}$/;
const dimension = s => String(s ?? '').replace(/^minecraft:/, '');

export class Pointing {
  constructor(path, owner, now = Date.now) { this.path=path; this.owner=owner; this.now=now; this.captured=new Map(); }
  read(bot) {
    if (!this.path || !this.owner || !bot?.entity) return null;
    try {
      if (statSync(this.path).size>32768) return null;
      const data=JSON.parse(readFileSync(this.path,'utf8'));
      if(data.version!==1 || !UUID.test(data.session) || !Array.isArray(data.selections) || data.selections.length>8) return null;
      return data;
    } catch { return null; }
  }
  valid(s,bot) {
    const now=this.now();
    return s && UUID.test(s.id) && s.owner===this.owner && UUID.test(s.player_uuid)
        && UUID.test(s.world) && dimension(s.dimension)===dimension(bot.game?.dimension)
        && Number.isSafeInteger(s.created_at) && Number.isSafeInteger(s.expires_at)
        && s.created_at<=now && s.expires_at>now && s.expires_at-s.created_at<=60000
        && Array.isArray(s.points) && s.points.length>=1 && s.points.length<=2
        && s.points.every(p => ['x','y','z'].every(k=>Number.isInteger(p[k]) && Math.abs(p[k])<30000000)
          && p.y>=-64 && p.y<=319 && /^[a-z0-9_]{1,64}$/.test(p.block)
          && Array.isArray(p.face) && p.face.length===3 && p.face.every(Number.isInteger)
          && p.face.reduce((n,v)=>n+Math.abs(v),0)===1);
  }
  selections(bot) { return (this.read(bot)?.selections ?? []).filter(s=>this.valid(s,bot)); }
  latest(bot) {
    const data=this.read(bot);
    if(!data) return null;
    let s=data.selections.filter(s=>this.valid(s,bot)).at(-1), source='owner_pointer';
    if(!s && this.valid(data.gaze,bot) && this.now()-data.published_at<1500) {
      source='owner_gaze';
      s={...data.gaze,created_at:this.now(),expires_at:this.now()+60000};
      this.captured.set(s.id,{...s,session:data.session});
      for(const [id,value] of this.captured) if(value.expires_at<=this.now()) this.captured.delete(id);
      while(this.captured.size>64) this.captured.delete(this.captured.keys().next().value);
    }
    return s ? { selection_id:s.id, points:s.points, expires_at:s.expires_at, source } : null;
  }
  resolve(bot,id) {
    const data=this.read(bot);
    if(!data) return null;
    const explicit=data.selections.find(s=>s.id===id && this.valid(s,bot));
    if(explicit) return explicit;
    const s=this.captured.get(id);
    return this.valid(s,bot) && s.session===data.session && data.presence?.world===s.world
      && data.presence?.player_uuid===s.player_uuid && this.now()-data.published_at<1500 ? s : null;
  }
}

export function selectedRegion(selection, floor, block) {
  if(selection.points.length!==2) return {error:'selection_needs_two_points'};
  const [a,b]=selection.points;
  if(floor && (a.y!==b.y || a.face[1]!==1 || b.face[1]!==1)) return {error:'selection_floor_not_level'};
  const args={};
  for(const k of ['x','y','z']) {
    args[k+'1']=Math.min(a[k],b[k])+(floor && k==='y'?1:0);
    args[k+'2']=Math.max(a[k],b[k])+(floor && k==='y'?1:0);
  }
  if(floor) args.block=block;
  return regionArgs(args,floor);
}

export async function actOnSelection(bot,args,token,ctx) {
  const {Failed,watched,guard}=ctx;
  const fail=reason=>{throw new Failed(reason);};
  const s=bot.pointing?.resolve(bot,args.selection_id);
  if(!s) fail('selection_expired');
  const p=s.points[0], pos=new Vec3(p.x,p.y,p.z);
  const check=()=>{
    if(!bot.pointing?.resolve(bot,args.selection_id)) fail('selection_expired');
    for(const q of s.points) {
      if(bot.blockAt(new Vec3(q.x,q.y,q.z))?.name!==q.block) fail('selection_changed');
    }
  };
  check();
  if(s.points.some(q=>new Vec3(q.x,q.y,q.z).distanceTo(bot.entity.position)>32)) fail('region_too_far');
  if(args.action==='clear' || args.action==='floor') {
    const r=selectedRegion(s,args.action==='floor',args.block);
    if(r.error) fail(r.error);
    return editRegion(bot,r.args,token,ctx,args.action==='floor');
  }
  if(s.points.length!==1) fail('selection_needs_one_point');
  await guard?.idle(token);
  if(token.cancelled) return;
  bot.pathfinder.setMovements(carefulMovements(bot));
  if(args.action==='move') {
    // The selected surface is a landmark; stop beside it, never inside the block.
    await watched(bot,()=>bot.pathfinder.goto(new goals.GoalNear(p.x,p.y+1,p.z,2)));
    if(!token.cancelled) { check(); return {selection_id:s.id,arrived:true}; }
    return;
  }
  if(args.action!=='recover' || p.block!=='crafting_table') fail('unsupported_selected_block');
  const count=()=>bot.inventory.items().filter(i=>i.name===p.block).reduce((n,i)=>n+i.count,0);
  const before=count();
  await watched(bot,()=>bot.pathfinder.goto(new goals.GoalNear(p.x,p.y,p.z,2)));
  if(token.cancelled) return;
  check();
  if(bot.tool?.equipForBlock) await bot.tool.equipForBlock(bot.blockAt(pos),{});
  if(token.cancelled) return;
  check();
  await bot.dig(bot.blockAt(pos));
  if(token.cancelled) return;
  await watched(bot,()=>bot.pathfinder.goto(new goals.GoalBlock(p.x,p.y,p.z)));
  for(let i=0;i<30 && !token.cancelled && count()<=before;i++) await bot.waitForTicks(2);
  if(token.cancelled) return;
  if(bot.blockAt(pos)?.name!=='air' || count()<=before) fail('objective_unverified');
  return {selection_id:s.id,recovered:1};
}
