// マイクラの知識の窓口（MCP）。docs/game-knowledge-design-ja.md。
// - シエルの会話サーバーが、マイクラで遊んでいる間だけ、ここの道具を心に渡す（CIEL_GAME_KNOWLEDGE）。
// - 道具は読むだけ。ゲームの中は動かさない。料金もかからない。
//   minecraft_facts：minecraft-data（体と同じ版）から正確な値を返す
//   minecraft_search：手元に置いた Minecraft Wiki（1.21.11 の時点）を調べる（Wiki を取り出してから足す）
// - 待ち受けは KNOWLEDGE_HOST（既定 127.0.0.1）だけ。体と同じく host のネットワークで動くので、全部のアドレスで開くと外から見える。
// - MCP の streamable HTTP を、会話を覚えない形（stateless）で開く。呼ばれるたびに窓口を作って答える。
import { existsSync } from 'node:fs';
import http from 'node:http';
import { join } from 'node:path';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { z } from 'zod';

import { Facts, KINDS } from './facts.js';
import { WikiIndex } from './wiki-index.js';

const HOST = process.env.KNOWLEDGE_HOST ?? '127.0.0.1';
const PORT = Number(process.env.KNOWLEDGE_PORT ?? 8770);
const VERSION = process.env.MC_VERSION ?? '1.21.11';
const MAX_BODY = 64 * 1024;
const DATA = process.env.KNOWLEDGE_DATA ?? '/app/knowledge-data';
const WIKI = join(DATA, 'wiki.sqlite');

const log = (...a) => console.log(new Date().toISOString(), ...a);
const facts = new Facts(VERSION);
// 手元の Wiki（wiki-fetch.js で取り出した物）。まだ無ければ、調べる道具は not_ready を返す。取り出し終えたら窓口を入れ直す
let wiki = null;
function openWiki() {
  if (wiki || !existsSync(WIKI)) return wiki;
  try {
    wiki = new WikiIndex(WIKI);
    log('手元の Wiki を開いた', JSON.stringify(wiki.counts()), JSON.stringify(wiki.meta()));
  } catch (e) {
    log('手元の Wiki を開けない', e?.message ?? e);
  }
  return wiki;
}

export function makeServer() {
  const server = new McpServer({ name: 'minecraft-knowledge', version: '1.0.0' });
  server.registerTool('minecraft_facts', {
    title: 'マイクラの正確なデータ',
    description: `Minecraft Java ${VERSION} の正確なデータ（シエルの体と同じ版）を引く。`
      + 'block：硬さ・掘るのに要るいちばん弱い道具（null なら素手で取れる）・落ちる物。'
      + 'item／recipe：作り方（材料と数・作業台が要るか）と、何も持っていないところから作るときに集める物（from_scratch.gather）。食べ物なら満腹度。'
      + 'mob：敵か・大きさ・倒すと落とす物。biome：気温・雨・次元。effect・enchantment：説明。'
      + 'name は英語の ID（cobblestone・iron_ore・zombie など）。見つからなければ near に似た ID が返る。',
    inputSchema: {
      kind: z.enum(KINDS).describe('調べる種類'),
      name: z.string().min(1).max(64).describe('英語の ID（例 stone_pickaxe）'),
    },
  }, async ({ kind, name }) => {
    const r = facts.lookup(kind, name);
    log('facts', kind, name, r.found ? 'found' : 'not_found');
    return { content: [{ type: 'text', text: JSON.stringify(r) }] };
  });
  server.registerTool('minecraft_search', {
    title: 'マイクラの知識を調べる',
    description: `手元に置いた Minecraft Wiki（英語、Java ${VERSION} が出たころの版。本文と表）を調べ、合う見出しを 3 つまで返す。`
      + '世界のどこに何があるか（鉱石の高さ・構造物・バイオーム）・どうすれば手に入るか・仕組み・遊び方を調べるときに使う。'
      + 'question は英語の短い言葉（例 stone generation height、where to find sand、how to tame a wolf）。'
      + '正確な数・作り方・要る道具は minecraft_facts のほうが確か。',
    inputSchema: { question: z.string().min(2).max(200).describe('英語の短い言葉') },
  }, async ({ question }) => {
    const w = openWiki();
    const r = w ? { status: 'ok', results: w.search(question) } : { status: 'not_ready' };
    log('search', question, r.status, r.results?.length ?? 0);
    return { content: [{ type: 'text', text: JSON.stringify(r) }] };
  });
  return server;
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY) throw new Error('too_large');
    chunks.push(c);
  }
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : undefined;
}

const httpServer = http.createServer(async (req, res) => {
  if (!req.url?.startsWith('/mcp')) {
    res.writeHead(404).end();
    return;
  }
  if (req.method !== 'POST') {   // stateless なので、待ち受けの GET・終わりの DELETE は受けない
    res.writeHead(405, { Allow: 'POST' }).end();
    return;
  }
  let body;
  try {
    body = await readBody(req);
  } catch {
    res.writeHead(400).end();
    return;
  }
  const server = makeServer();
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
  res.on('close', () => {
    transport.close();
    server.close();
  });
  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, body);
  } catch (e) {
    log('答えられない', e?.message ?? e);
    if (!res.headersSent) res.writeHead(500).end();
  }
});

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/').split('/').pop())) {
  httpServer.listen(PORT, HOST, () => log(`マイクラの知識の窓口 http://${HOST}:${PORT}/mcp（版 ${VERSION}）`));
  for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => { httpServer.close(); process.exit(0); });
}

export { httpServer };
