import { readFileSync, statSync } from 'node:fs';
const UUID = /^[a-f0-9-]{36}$/;
const dimension = s => String(s ?? '').replace(/^minecraft:/, '');

export class Pointing {
  // given: what latest() handed the conversation, so a work submitted a few seconds later can
  // still be resolved by its id after the owner looks elsewhere.
  constructor(path, owner, now = Date.now) { this.path=path; this.owner=owner; this.now=now; this.given=new Map(); }
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
    }
    if(!s) return null;
    const ref={ selection_id:s.id, points:s.points, expires_at:s.expires_at, source };
    for(const [id,g] of this.given) if(g.expires_at<=this.now()) this.given.delete(id);
    this.given.set(ref.selection_id, ref);
    while(this.given.size>16) this.given.delete(this.given.keys().next().value);
    return ref;
  }
  // What the owner pointed at, by the id the conversation was given; null once it has expired.
  place(bot,id) {
    if(!UUID.test(String(id))) return null;
    const s=this.selections(bot).find(s=>s.id===id);
    if(s) return { selection_id:s.id, points:s.points, expires_at:s.expires_at, source:'owner_pointer' };
    const g=this.given.get(id);
    return g && g.expires_at>this.now() ? g : null;
  }
}

// The words a work's request carries for Mindcraft's planner about the place the owner meant.
export function placeNote(ref) {
  const at = p => `x=${p.x}, y=${p.y}, z=${p.z}（${p.block}）`;
  if (ref.points.length===1) {
    const how = ref.source==='owner_gaze' ? '見ていた' : '指していた';
    return `持ち主が依頼のときに${how}ブロックは ${at(ref.points[0])}。依頼の「ここ」「あそこ」「これ」はこの場所のこと。`;
  }
  const [a,b]=ref.points;
  const span = k => a[k]===b[k] ? `${k}=${a[k]}` : `${k}=${Math.min(a[k],b[k])}〜${Math.max(a[k],b[k])}`;
  return `持ち主が依頼のときに選んでいた範囲は ${['x','y','z'].map(span).join(', ')}（端のブロックは ${a.block} と ${b.block}）。依頼の「ここ」「この辺」「この範囲」はこの範囲のこと。`;
}
