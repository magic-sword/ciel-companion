import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Facts, near, normalize } from '../src/knowledge/facts.js';

const facts = new Facts('1.21.11');

test('ブロック：要る道具と落ちる物', () => {
  const stone = facts.lookup('block', 'stone');
  assert.equal(stone.tool_needed, 'wooden_pickaxe');
  assert.ok(stone.drops.some((d) => d.item === 'cobblestone' && d.without_silk_touch && d.chance === 1));
  assert.equal(facts.lookup('block', 'iron_ore').tool_needed, 'stone_pickaxe');
  assert.equal(facts.lookup('block', 'dirt').tool_needed, null);   // 素手で取れる
});

test('作り方：ふつうの材料を先に、何も無いところから集める物', () => {
  const sp = facts.lookup('item', 'stone_pickaxe');
  assert.deepEqual(sp.ways[0].ingredients, { cobblestone: 3, stick: 2 });
  assert.equal(sp.ways[0].needs_crafting_table, true);
  assert.deepEqual(sp.from_scratch.gather, { cobblestone: 3, oak_log: 2 });
  assert.deepEqual(facts.lookup('recipe', 'wooden_pickaxe').from_scratch.gather, { oak_log: 3 });
  assert.equal(facts.lookup('item', 'diamond').craftable, true);   // ダイヤのブロックから戻せる
  assert.equal(facts.lookup('item', 'oak_log').craftable, false);
  assert.equal(facts.lookup('item', 'bread').food.foodPoints, 5);
});

test('生き物・バイオーム・効果', () => {
  const z = facts.lookup('mob', 'zombie');
  assert.equal(z.type, 'hostile');
  assert.ok(z.drops.some((d) => d.item === 'rotten_flesh'));
  assert.equal(facts.lookup('biome', 'plains').precipitation, true);
  assert.equal(facts.lookup('effect', 'Speed').name, 'speed');
});

test('名前の揺れと、見つからないとき', () => {
  assert.equal(normalize('minecraft:Cobble Stone'), 'cobble_stone');
  assert.equal(facts.lookup('block', 'Cobblestone').name, 'cobblestone');
  const miss = facts.lookup('item', 'cobble');
  assert.equal(miss.found, false);
  assert.equal(miss.near[0], 'cobblestone');
  assert.equal(facts.lookup('weapon', 'sword').error, 'unknown_kind');
  assert.deepEqual(near(['apple', 'stone', 'stick'], 'stoen').slice(0, 1), ['stone']);
});

// 試験の記事は作り物（Wiki の文は Git に入れない）
const PAGE = `<div class="mw-parser-output">
<table class="infobox-rows"><tbody><tr><th>Tool</th><td>Wooden Pickaxe</td></tr><tr><th>Hardness</th><td>1.5</td></tr></tbody></table>
<pre class="history-json">{"title": "secret"}</pre>
<p>Rock is a common block found underground<sup class="reference">[1]</sup>.</p>
<div class="mw-heading mw-heading2"><h2 id="Obtaining">Obtaining</h2></div>
<div class="mw-heading mw-heading3"><h3>Natural generation</h3></div>
<p>Rock generates below dirt in most biomes.</p>
<table class="wikitable"><tbody><tr><th>Level</th><th>Chance</th></tr><tr><td>0</td><td>high</td></tr><tr><td>64</td><td>low</td></tr></tbody></table>
<div class="mw-heading mw-heading2"><h2>History</h2></div>
<p>Added in Classic.</p>
<div class="mw-heading mw-heading3"><h3>Java Edition</h3></div>
<p>Changed in 1.0.</p>
<div class="mw-heading mw-heading2"><h2>Usage</h2></div>
<ul><li>Building</li><li>Crafting stone tools</li></ul>
</div>`;

test('Wiki の記事を、見出しごとのかたまりにする（表を残し、歴史と隠しデータを落とす）', async () => {
  const { chunksOf } = await import('../src/knowledge/wiki-text.js');
  const c = chunksOf('Rock', PAGE);
  assert.deepEqual(c.map((x) => x.section), ['Overview', 'Obtaining > Natural generation', 'Usage']);
  assert.match(c[0].text, /Tool: Wooden Pickaxe/);
  assert.doesNotMatch(c[0].text, /secret|\[1\]/);
  assert.match(c[1].text, /Level: 0; Chance: high/);
  assert.match(c[2].text, /- Crafting stone tools/);
  assert.ok(c.every((x) => !/Classic|1\.0/.test(x.text)));
  const long = chunksOf('Rock', `<div class="mw-parser-output">${'<p>' + 'word '.repeat(100) + '</p>'.repeat(1)}${'<p>more text here</p>'.repeat(80)}</div>`, 200);
  assert.ok(long.length > 3 && long.every((x) => x.text.length <= 600));
});

test('手元の Wiki を調べる（FTS5 があるときだけ）', async (t) => {
  const { WikiIndex, hasFts5 } = await import('../src/knowledge/wiki-index.js');
  if (!hasFts5()) return t.skip('この Node の SQLite には FTS5 が無い（体のイメージの Node 22.23 にはある）');
  const { chunksOf } = await import('../src/knowledge/wiki-text.js');
  const w = new WikiIndex(':memory:');
  w.addPage('Rock', { oldid: 1, url: 'https://minecraft.wiki/w/Rock?oldid=1', chunks: chunksOf('Rock', PAGE) });
  w.addPage('Sand', { oldid: 2, url: 'u2', chunks: [{ section: 'Natural generation', text: 'Sand generates in deserts and on beaches.' }] });
  w.addPage('Gone', { status: 'missing' });
  assert.deepEqual(w.counts(), { pages: 2, chunks: 4 });
  assert.equal(w.done('Gone'), true);
  const r = w.search('where does rock generate');
  assert.equal(r[0].title, 'Rock');
  assert.equal(r[0].section, 'Obtaining > Natural generation');
  assert.equal(r[0].source, 'https://minecraft.wiki/w/Rock?oldid=1');
  assert.equal(w.search('sand beaches')[0].title, 'Sand');
  assert.deepEqual(w.search('the of'), []);
  // 入れ直したら、前のかたまりは消える
  w.addPage('Sand', { oldid: 3, url: 'u3', chunks: [{ section: 'Overview', text: 'Sand is a gravity block.' }] });
  assert.equal(w.search('deserts').length, 0);
});
