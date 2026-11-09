// Minecraft Wiki から、1.21.11 が出たころの版を記事ごとに取り出して、索引（wiki-index.js）に入れる。1 回だけ手で動かす。
// docs/games/minecraft/minecraft-design-ja.md。
//   node src/knowledge/wiki-fetch.js [--list-only] [--limit N] [--date 2025-12-10T00:00:00Z]
// - 記事の一覧：カテゴリ（ROOTS）から 2 段下までの Java 版の記事。版ごとの更新記事・開発版・ほかのゲームの記事は入れない。
// - 版：各記事の DATE より前の最後の版を API で引き、その版を描き出した HTML（action=parse&oldid）を取る。
// - 負担をかけない：1 秒に 1 回まで（REQUEST_MS）。User-Agent に用途を書く（連絡先にユーザーのメールは入れない）。
// - 途中で止めても、もう一度動かせば続きから（取り出し済みの記事は飛ばす）。
// - Wiki の文は CC BY-NC-SA 3.0。自分たちだけで使い、Git・デプロイに入れない。出典（記事の URL と版）を残す。
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { WikiIndex } from './wiki-index.js';
import { chunksOf } from './wiki-text.js';

const API = 'https://minecraft.wiki/api.php';
const UA = 'CielCompanion-knowledge/1.0 (personal non-commercial home assistant; one-time snapshot at 1 request per second)';
const REQUEST_MS = 1000;
const DATA = process.env.KNOWLEDGE_DATA ?? '/app/knowledge-data';
const ROOTS = ['Blocks', 'Items', 'Mobs', 'Biomes', 'Generated structures', 'Structures', 'Gameplay', 'Tutorials', 'Environment',
  'Enchantments', 'Effects', 'Food', 'Tools', 'Weapons', 'Armor', 'Dimensions', 'Villagers'];
const DEPTH = 2;
// 入れないカテゴリ・記事
const SKIP_CATEGORY = /Movie|Earth|Education|Story Mode|Dungeons|Legends|Spin-off|renders|Renders|images|Images|Textures|Sounds|Planned|Removed|Unused|Joke|April Fools|profiles|Bedrock Edition|Pocket Edition|Legacy Console|3DS|Development|Disambiguation|Historical|Upcoming|Cut |Mods|Navbox|Templates|Pages/;
const SKIP_TITLE = /LEGO|Hour of Code|Skin Pack|Mash-up|Texture Pack|\(trailer\)|[Tt]railer$|\.dat format| format$|^Invalid data value|Minecraft Movie|^Minecraft Live|^MINECON|^(Java|Bedrock|Pocket|Legacy Console|Education|New Nintendo 3DS|Pi) Edition|^\d+w\d+[a-z]$|Pre-[Rr]elease|Release Candidate|\/(Renders|DV|Development|Structure|Assets|BE|LCE)\b|^Minecraft (Dungeons|Legends|Earth|Story Mode)|^Tutorials\/Pre-/;

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : dflt;
};
const DATE = opt('date', '2025-12-10T00:00:00Z');   // 1.21.11 は 2025-12-09 に出た
const LIMIT = Number(opt('limit', Infinity));
const LIST_ONLY = args.includes('--list-only');

const log = (...a) => console.log(new Date().toISOString(), ...a);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let last = 0;

async function api(params) {
  for (let attempt = 0; ; attempt++) {
    const gap = last + REQUEST_MS - Date.now();
    if (gap > 0) await wait(gap);
    last = Date.now();
    const url = `${API}?${new URLSearchParams({ format: 'json', formatversion: '2', ...params })}`;
    try {
      const res = await fetch(url, { headers: { 'User-Agent': UA } });
      if (res.status === 429 || res.status >= 500) throw new Error(`HTTP ${res.status}`);
      if (!res.ok) return { error: `HTTP ${res.status}` };
      return await res.json();
    } catch (e) {
      if (attempt >= 4) throw e;
      log('待ってやり直す', e.message);
      await wait(REQUEST_MS * 10 * (attempt + 1));
    }
  }
}

async function members(category, type) {
  const out = [];
  let cont = {};
  for (;;) {
    const j = await api({ action: 'query', list: 'categorymembers', cmtitle: `Category:${category}`, cmtype: type, cmlimit: '500', ...cont });
    out.push(...(j.query?.categorymembers ?? []));
    if (!j.continue) return out;
    cont = j.continue;
  }
}

async function listTitles() {
  const titles = new Set();
  const seen = new Set();
  let level = ROOTS;
  for (let depth = 0; depth <= DEPTH && level.length; depth++) {
    const next = [];
    for (const cat of level) {
      if (seen.has(cat)) continue;
      seen.add(cat);
      for (const p of await members(cat, 'page')) if (p.ns === 0 && !SKIP_TITLE.test(p.title)) titles.add(p.title);
      if (depth < DEPTH) {
        for (const s of await members(cat, 'subcat')) {
          const name = s.title.replace(/^Category:/, '');
          if (!SKIP_CATEGORY.test(name)) next.push(name);
        }
      }
    }
    log(`カテゴリ ${depth} 段目まで：記事 ${titles.size}`);
    level = next;
  }
  return [...titles].sort();
}

async function fetchPage(index, title) {
  const r = await api({ action: 'query', prop: 'revisions', titles: title, rvlimit: '1', rvstart: DATE, rvdir: 'older', rvprop: 'ids|timestamp' });
  const page = r.query?.pages?.[0];
  const rev = page?.revisions?.[0];
  if (!rev) {   // その日にはまだ無かった記事
    index.addPage(title, { status: 'missing' });
    return 0;
  }
  const p = await api({ action: 'parse', oldid: String(rev.revid), prop: 'text', disablelimitreport: '1', disableeditsection: '1' });
  const html = p.parse?.text;
  if (!html) {
    index.addPage(title, { status: 'error' });
    return 0;
  }
  const chunks = chunksOf(title, html);
  const url = `https://minecraft.wiki/w/${encodeURIComponent(title.replace(/ /g, '_'))}?oldid=${rev.revid}`;
  index.addPage(title, { oldid: rev.revid, timestamp: rev.timestamp, url, chunks });
  return chunks.length;
}

async function main() {
  mkdirSync(DATA, { recursive: true });
  const index = new WikiIndex(join(DATA, 'wiki.sqlite'));
  log(`記事の一覧を作る（${ROOTS.length} のカテゴリから ${DEPTH} 段下まで）`);
  const titles = await listTitles();
  log(`記事 ${titles.length}`);
  if (LIST_ONLY) {
    console.log(titles.join('\n'));
    return;
  }
  index.setMeta('source', 'https://minecraft.wiki (CC BY-NC-SA 3.0)');
  index.setMeta('as_of', DATE);
  index.setMeta('game_version', 'Java Edition 1.21.11');
  let n = 0;
  for (const title of titles) {
    if (n >= LIMIT) break;
    if (index.done(title)) continue;
    try {
      await fetchPage(index, title);
    } catch (e) {
      log('取り出せない', title, e.message);
      index.addPage(title, { status: 'error' });
    }
    n += 1;
    if (n % 50 === 0) log(`取り出した ${n}`, JSON.stringify(index.counts()));
  }
  index.setMeta('fetched_at', new Date().toISOString());
  log('終わり', JSON.stringify(index.counts()));
  index.close();
}

main().catch((e) => {
  log('止まった', e?.stack ?? e);
  process.exit(1);
});
