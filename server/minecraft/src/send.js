// 手元から体を動かして確かめる（会話サーバーの代わり）。届いた知らせを表示する。
//   node src/send.js                                   つないで、様子と出来事を見るだけ
//   node src/send.js '{"type":"do","id":1,"skill":"follow"}'
//   node src/send.js '{"type":"stop"}'
// v は省いてよい（1 を足す）。Ctrl+C で切る（切ると、体は今の技を止めてその場で待つ）。
// SECONDS=30 を付けると、30 秒で切る（docker compose exec -T から使うとき。外から止めても、コンテナの中では残るため）。
import WebSocket from 'ws';

const url = process.env.BODY_URL ?? `ws://127.0.0.1:${process.env.BODY_PORT ?? 8768}`;
const ws = new WebSocket(url);
if (process.env.SECONDS) setTimeout(() => ws.close(), Number(process.env.SECONDS) * 1000);
ws.on('open', () => {
  for (const arg of process.argv.slice(2)) ws.send(JSON.stringify({ v: 1, ...JSON.parse(arg) }));
});
ws.on('message', (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.type === 'state' && process.env.QUIET_STATE) return;
  console.log(JSON.stringify(m));
});
ws.on('close', () => process.exit(0));
ws.on('error', (err) => {
  console.error(`つなげない ${url}：${err.code ?? err.message}`);
  process.exit(1);
});
