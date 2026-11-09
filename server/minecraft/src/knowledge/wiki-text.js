// Minecraft Wiki の記事（action=parse の HTML）を、調べられるかたまりにする。docs/games/minecraft/minecraft-design-ja.md。
// - 本文と表を残す（MineDojo に倣う。鉱石の高さごとの出やすさ・宝箱の中身・作り方は表にある）。表は 1 行ずつ「見出し：値」にする。
// - 版の歴史・ギャラリー・脚注・ナビゲーション・音・データ値などは落とす（今の版の知識だけにする）。
// - 見出し（h2・h3）ごとに区切り、長ければ CHUNK_CHARS ほどで分ける。
import * as cheerio from 'cheerio';

export const CHUNK_CHARS = 800;
// 落とす見出し（h2。その下の h3 も一緒に落とす）
const DROP_SECTIONS = /^(History|Development|Gallery|Screenshots|In other media|References|External links|Navigation|Videos|Sounds|Issues|Data history|Data values|Achievements|Advancements|Trivia|See also|Notes|Renders|Textures|Concept artwork|Mojang screenshots|Merchandise)$/i;
// 落とす部品
const DROP_ELEMENTS = [
  'script', 'style', 'sup.reference', '.mw-editsection', '.toc', '#toc', '.navbox', '.mw-references-wrap', '.reflist',
  '.gallery', '.noprint', '.mw-empty-elt', '.hatnote', '.msgbox', '.ambox', '.sprite-file', 'figure', '.thumb',
  '.load-page', '.pixel-image', '.mobile-only', '.edition-note', '.history-json', '.navigation-not-searchable', 'pre',
].join(',');

const clean = (s) => s.replace(/ /g, ' ').replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();

// 表を文字にする。1 行目が見出しの行なら、各行を「見出し：値」で書く
function tableText($, table) {
  const rows = $(table).find('tr').toArray().map((tr) => $(tr).children('th,td').toArray().map((c) => clean($(c).text()).replace(/\n/g, ' ')));
  if (!rows.length) return '';
  const isHead = $(table).find('tr').first().children('td').length === 0;
  const head = isHead ? rows[0] : null;
  const body = isHead ? rows.slice(1) : rows;
  const lines = body.filter((r) => r.some(Boolean)).map((r) => {
    if (head && head.length === r.length) return r.map((v, i) => (head[i] ? `${head[i]}: ${v}` : v)).filter((x) => x.trim()).join('; ');
    if (r.length === 2) return `${r[0]}: ${r[1]}`;   // インフォボックス（見出し・値の 2 列）
    return r.filter(Boolean).join(' | ');
  });
  return lines.join('\n');
}

function blockText($, el) {
  const tag = el.tagName?.toLowerCase();
  if (tag === 'table') return tableText($, el);
  if (tag === 'ul' || tag === 'ol') return $(el).children('li').toArray().map((li) => `- ${clean($(li).text()).replace(/\n/g, ' ')}`).join('\n');
  if (tag === 'dl') return $(el).children().toArray().map((d) => clean($(d).text())).filter(Boolean).join('\n');
  // 中に表があれば、表は表として読む
  const tables = $(el).find('table').toArray();
  if (tables.length) {
    const parts = tables.map((t) => tableText($, t));
    $(el).find('table').remove();
    return [clean($(el).text()), ...parts].filter(Boolean).join('\n');
  }
  return clean($(el).text());
}

function headingOf($, el) {
  const tag = el.tagName?.toLowerCase();
  const h = /^h[2-4]$/.test(tag) ? $(el) : $(el).hasClass('mw-heading') ? $(el).find('h2,h3,h4').first() : null;
  if (!h || !h.length) return null;
  return { level: Number(h[0].tagName.slice(1)), title: clean(h.text()) };
}

// HTML → [{ section, text }]（section は「Natural generation」「Usage > Smelting ingredient」など。始めは Overview）
export function sectionsOf(html) {
  const $ = cheerio.load(html);
  $(DROP_ELEMENTS).remove();
  const root = $('.mw-parser-output').first().length ? $('.mw-parser-output').first() : $('body');
  const out = [];
  let h2 = 'Overview';
  let h3 = null;
  let dropping = false;
  let buf = [];
  const flush = () => {
    const text = buf.join('\n').trim();
    if (text && !dropping) out.push({ section: h3 ? `${h2} > ${h3}` : h2, text });
    buf = [];
  };
  for (const el of root.children().toArray()) {
    const h = headingOf($, el);
    if (h) {
      flush();
      if (h.level === 2) {
        h2 = h.title;
        h3 = null;
        dropping = DROP_SECTIONS.test(h2);
      } else if (h.level === 3) {
        h3 = h.title;
      }
      continue;
    }
    const t = blockText($, el);
    if (t) buf.push(t);
  }
  flush();
  return out;
}

// かたまりに分ける（段落の切れ目で、CHUNK_CHARS ほど）
export function chunksOf(title, html, size = CHUNK_CHARS) {
  const chunks = [];
  for (const { section, text } of sectionsOf(html)) {
    let cur = '';
    for (const para of text.split('\n')) {
      if (cur && cur.length + para.length + 1 > size) {
        chunks.push({ title, section, text: cur });
        cur = '';
      }
      cur = cur ? `${cur}\n${para}` : para.slice(0, size * 2);
    }
    if (cur) chunks.push({ title, section, text: cur });
  }
  return chunks;
}
