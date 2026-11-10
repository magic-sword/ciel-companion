// Bounded construction primitives; no commands, creative mode, or out-of-region edits.
import { Vec3 } from 'vec3';
import pathfinderPkg from 'mineflayer-pathfinder';
import { carefulMovements, NATURAL } from './movements.js';
const { goals } = pathfinderPkg;
export const BUILD_BLOCKS = ['dirt', 'cobblestone', 'stone', 'oak_planks', 'glass'];
export function regionArgs(a, build = false) {
  const fields = ['x1', 'y1', 'z1', 'x2', 'y2', 'z2'];
  if (!a || fields.some(k => !Number.isInteger(a[k]) || Math.abs(a[k]) > 29999984)
      || a.y1 < -64 || a.y2 > 319 || a.x1 > a.x2 || a.y1 > a.y2 || a.z1 > a.z2
      || (a.x2-a.x1+1)*(a.y2-a.y1+1)*(a.z2-a.z1+1) > 64
      || (build && !BUILD_BLOCKS.includes(a.block))) return { error: 'bad_args' };
  return { args: Object.fromEntries([...fields, ...(build ? ['block'] : [])].map(k => [k, a[k]])) };
}
export function cells(a, build) {
  const out = [];
  for (let y=a.y1; y<=a.y2; y++) for (let x=a.x1; x<=a.x2; x++) for (let z=a.z1; z<=a.z2; z++) out.push(new Vec3(x,y,z));
  return out.sort((p,q) => build ? p.y-q.y : q.y-p.y);
}
export function regionStances(bot, a, target) {
  const out=[];
  for (let x=target.x-3;x<=target.x+3;x++) for (let z=target.z-3;z<=target.z+3;z++) {
    if (x>=a.x1 && x<=a.x2 && z>=a.z1 && z<=a.z2) continue;
    for (let y=target.y-3;y<=target.y+1;y++) {
      const p=new Vec3(x,y,z), foot=bot.blockAt(p), head=bot.blockAt(p.offset(0,1,0)), floor=bot.blockAt(p.offset(0,-1,0));
      if (foot?.name==='air' && head?.name==='air' && floor?.boundingBox==='block'
          && p.offset(.5,1.62,.5).distanceTo(target.offset(.5,.5,.5))<4.3) out.push(p);
    }
  }
  return out.sort((p,q)=>p.distanceTo(bot.entity.position)-q.distanceTo(bot.entity.position));
}
export async function editRegion(bot, a, token, { guard, Failed, watched }, build) {
  const positions = cells(a, build), deadline = Date.now()+110000;
  const fail = reason => { throw new Failed(reason); };
  const read = p => { const b=bot.blockAt(p); if (!b) fail('unloaded_region'); return b; };
  const air = b => ['air','cave_air','void_air'].includes(b.name);
  if (positions.some(p => p.distanceTo(bot.entity.position)>32)) fail('region_too_far');
  // Preflight all cells: never partially clear a known building or begin without materials.
  let required=0;
  for (const p of positions) {
    const b=read(p);
    if (build) { if (b.name!==a.block) { if (!air(b)) fail('occupied_region'); required++; } }
    else if (!air(b) && !NATURAL.test(b.name)) fail('protected_block');
  }
  if (build && bot.inventory.items().filter(i=>i.name===a.block).reduce((n,i)=>n+i.count,0)<required) fail('missing_materials');
  let changed=0;
  for (const p of positions) {
    if (token.cancelled) return { changed };
    if (Date.now()>deadline) fail('region_timeout');
    await guard?.idle(token);
    if (token.cancelled) return { changed };
    let b=read(p);
    if (build ? b.name===a.block : air(b)) continue;
    bot.pathfinder.setMovements(carefulMovements(bot));
    // Stay outside the edited columns for placement too: GoalNear may stop inside
    // the next block and the server correctly rejects placing into our own body.
    const stances=regionStances(bot,a,p);
    if (!stances.length) fail('unsafe_stance');
    await watched(bot, () => bot.pathfinder.goto(new goals.GoalCompositeAny(stances.map(s=>new goals.GoalBlock(s.x,s.y,s.z)))));
    if (token.cancelled) return { changed };
    b=read(p);
    if (build) {
      if (!air(b)) fail('occupied_region');
      const item=bot.inventory.items().find(i=>i.name===a.block);
      if (!item) fail('missing_materials');
      const faces=[new Vec3(0,1,0),new Vec3(1,0,0),new Vec3(-1,0,0),new Vec3(0,0,1),new Vec3(0,0,-1)];
      const face=faces.find(f=>read(p.minus(f)).boundingBox==='block');
      if (!face) fail('no_support');
      await bot.equip(item,'hand');
      await bot.placeBlock(read(p.minus(face)),face);
    } else {
      if (!NATURAL.test(b.name)) fail('protected_block');
      if (Math.floor(bot.entity.position.x)===p.x && Math.floor(bot.entity.position.z)===p.z && p.y<bot.entity.position.y) fail('unsafe_stance');
      if (bot.tool?.equipForBlock) await bot.tool.equipForBlock(b,{});
      await bot.dig(b);
    }
    await bot.waitForTicks(2);
    if (token.cancelled) return { changed };
    if (build ? read(p).name!==a.block : !air(read(p))) fail('objective_unverified');
    changed++;
  }
  if (positions.some(p=>build ? read(p).name!==a.block : !air(read(p)))) fail('objective_unverified');
  return { changed, verified: positions.length };
}
