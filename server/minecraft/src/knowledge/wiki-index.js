// 手元に置いた Minecraft Wiki の索引（SQLite の全文検索 FTS5）。docs/games/minecraft/minecraft-design-ja.md。
// 置き場は KNOWLEDGE_DATA（既定 /app/knowledge-data）の wiki.sqlite。Git・デプロイの外。
// node:sqlite を使う（Node 22.23 の組み込み。手元の Node 22.14 は FTS5 が無いので、試験は FTS5 があるときだけ）。
import { DatabaseSync } from 'node:sqlite';

const SHOWN = 3;          // 返すかたまりの数
const PER_PAGE = 2;       // 同じ記事からは、ここまで（いろいろな記事から返す）
const TEXT_CHARS = 800;
const STOP = new Set(['a', 'an', 'the', 'of', 'in', 'on', 'to', 'for', 'and', 'or', 'is', 'are', 'how', 'what', 'where', 'when',
  'do', 'does', 'can', 'i', 'you', 'it', 'with', 'from', 'by', 'be', 'get', 'minecraft', 'which', 'find']);

export function hasFts5() {
  try {
    const d = new DatabaseSync(':memory:');
    d.exec('create virtual table t using fts5(a)');
    d.close();
    return true;
  } catch {
    return false;
  }
}

export class WikiIndex {
  constructor(path) {
    this.db = new DatabaseSync(path);
    this.db.exec(`
      create table if not exists meta (key text primary key, value text);
      create table if not exists pages (title text primary key, oldid integer, timestamp text, status text, chunks integer);
      create virtual table if not exists chunks using fts5(title, section, text, url unindexed, tokenize = 'porter unicode61');
    `);
  }

  close() {
    this.db.close();
  }

  setMeta(key, value) {
    this.db.prepare('insert into meta(key, value) values (?, ?) on conflict(key) do update set value = excluded.value').run(key, String(value));
  }

  meta() {
    return Object.fromEntries(this.db.prepare('select key, value from meta').all().map((r) => [r.key, r.value]));
  }

  done(title) {
    return Boolean(this.db.prepare('select 1 from pages where title = ? and status in (\'done\', \'missing\')').get(title));
  }

  // 記事を入れ直す（同じ題のかたまりは消してから入れる）
  addPage(title, { oldid = null, timestamp = null, url = null, chunks = [], status = 'done' }) {
    this.db.exec('begin');
    try {
      this.db.prepare('delete from chunks where title = ?').run(title);
      const ins = this.db.prepare('insert into chunks(title, section, text, url) values (?, ?, ?, ?)');
      for (const c of chunks) ins.run(c.title ?? title, c.section, c.text, url);
      this.db.prepare('insert into pages(title, oldid, timestamp, status, chunks) values (?, ?, ?, ?, ?) '
        + 'on conflict(title) do update set oldid = excluded.oldid, timestamp = excluded.timestamp, status = excluded.status, chunks = excluded.chunks')
        .run(title, oldid, timestamp, status, chunks.length);
      this.db.exec('commit');
    } catch (e) {
      this.db.exec('rollback');
      throw e;
    }
  }

  counts() {
    return {
      pages: this.db.prepare('select count(*) n from pages where status = \'done\'').get().n,
      chunks: this.db.prepare('select count(*) n from chunks').get().n,
    };
  }

  // 英語の短い言葉で調べる。合うかたまりを SHOWN まで（同じ記事からは PER_PAGE まで）
  search(question, shown = SHOWN) {
    const words = [...new Set((String(question).toLowerCase().match(/[a-z0-9]+/g) ?? []).filter((w) => !STOP.has(w)))].slice(0, 12);
    if (!words.length) return [];
    const q = words.map((w) => `"${w}"`).join(' OR ');
    // 題を重く、見出しを次に（bm25 は小さいほど合う）
    const rows = this.db.prepare(`select title, section, text, url, bm25(chunks, 8.0, 3.0, 1.0) as score
      from chunks where chunks match ? order by score limit 40`).all(q);
    const per = new Map();
    const out = [];
    for (const r of rows) {
      const n = per.get(r.title) ?? 0;
      if (n >= PER_PAGE) continue;
      per.set(r.title, n + 1);
      out.push({ title: r.title, section: r.section, text: r.text.slice(0, TEXT_CHARS), source: r.url });
      if (out.length >= shown) break;
    }
    return out;
  }
}
