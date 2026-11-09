// シエルが「見て知っている」ことだけを使う。docs/games/minecraft/minecraft-design-ja.md の 18 章。
// - ボットは周りのブロックを壁の向こうまで全部知っているが、プレイヤーは見えた物しか知らない。地中に埋まった鉱石の話をして
//   不自然だった（2026-11-06）。様子（state.js）に入れるブロック・敵と、集める（skills.js）ブロックは、ここで見えるか確かめる。
// - 見える：目の高さから、空気に面した面の真ん中へ視線を飛ばし、途中で別のブロックに当たらずに届く（向きは問わない。見回せば見える）。
// - 一度見たブロックは覚えておく（遠くへ行っても、さっき見た木へ戻れる）。掘ったブロックにつながる同じ種類のブロックも
//   知っていることにする（木の幹の上のほう。プレイヤーも、木が上へ続くのは分かる）。
import { Vec3 } from 'vec3';

const FACES = [new Vec3(1, 0, 0), new Vec3(-1, 0, 0), new Vec3(0, 1, 0), new Vec3(0, -1, 0), new Vec3(0, 0, 1), new Vec3(0, 0, -1)];
const REMEMBER = 4096;    // 覚えておくブロックの数（古いものから忘れる）
const HEAR = 5;           // 敵は、見えなくてもこの距離なら気づく（足音・うなり声）

const key = (p) => `${p.x},${p.y},${p.z}`;

// 空気（や草のような通り抜けられる物）に面しているか。埋まっていれば、どこからも見えない
export function exposedFaces(bot, pos) {
  return FACES.filter((f) => {
    const n = bot.blockAt(pos.plus(f));
    return n && (n.boundingBox === 'empty' || n.transparent);
  });
}

// 目から見えるか（空気に面したどれかの面に視線が届く）
export function canSee(bot, pos) {
  if (!bot?.entity) return false;
  const eye = bot.entity.position.offset(0, bot.entity.eyeHeight ?? 1.62, 0);
  for (const f of exposedFaces(bot, pos)) {
    const target = pos.offset(0.5 + f.x * 0.5, 0.5 + f.y * 0.5, 0.5 + f.z * 0.5);
    const dir = target.minus(eye);
    const range = dir.norm();
    if (range < 0.01) return true;
    // 草花のように当たりの形が無いブロックも、そのブロックに着いたら見えたとする
    const hit = bot.world.raycast(eye, dir.normalize(), range + 0.1,
      (b, iter) => b.position.equals(pos) || Boolean(iter.intersect(b.shapes, b.position)));
    if (hit && hit.position.equals(pos)) return true;
  }
  return false;
}

// 生き物が見えるか（目から体の真ん中へ、ブロックに当たらず届く）。近ければ見えなくても気づく
export function notices(bot, entity) {
  if (!bot?.entity || !entity?.position) return false;
  const eye = bot.entity.position.offset(0, bot.entity.eyeHeight ?? 1.62, 0);
  const target = entity.position.offset(0, (entity.height ?? 1.8) / 2, 0);
  const dir = target.minus(eye);
  const range = dir.norm();
  if (range <= HEAR) return true;
  if (!bot.world?.raycast) return true;
  return !bot.world.raycast(eye, dir.normalize(), range);
}

// 見て知っているブロック（体ごとに 1 つ）
const memories = new WeakMap();

function memory(bot) {
  let m = memories.get(bot);
  if (!m) memories.set(bot, (m = new Map()));
  return m;
}

export function remember(bot, pos, name) {
  const m = memory(bot);
  const k = key(pos);
  m.delete(k);
  m.set(k, name);
  while (m.size > REMEMBER) m.delete(m.keys().next().value);
}

// 見たことがあるか（今もその種類のままのときだけ）
export function known(bot, pos) {
  const m = memory(bot);
  const name = m.get(key(pos));
  if (!name) return false;
  if (bot.blockAt(pos)?.name !== name) {
    m.delete(key(pos));
    return false;
  }
  return true;
}

// 掘ったブロックのまわりの、同じ種類のブロックを知っていることにする（木の幹の上のほうなど）
export function rememberAround(bot, pos, matches) {
  for (const f of FACES) {
    const p = pos.plus(f);
    const b = bot.blockAt(p);
    if (b && matches(b.name)) remember(bot, p, b.name);
  }
}

// 今見えるか、前に見たか。見えたら覚える
export function knows(bot, pos) {
  if (known(bot, pos)) return true;
  if (!canSee(bot, pos)) return false;
  const name = bot.blockAt(pos)?.name;
  if (name) remember(bot, pos, name);
  return true;
}
