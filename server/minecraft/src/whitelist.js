// アカウントの確認なし（online-mode=false）のサーバー用の whitelist.json を出す。
// そのサーバーでのプレイヤーの ID は「OfflinePlayer:名前」の MD5 から作る（UUID v3）。rcon-cli の whitelist add は
// ふつうのアカウントの ID で登録するので、そのままでは入れない（2026-11-05、自宅サーバーで確かめた）。
//   node src/whitelist.js Ciel Hakase4364 > whitelist.json
import { createHash } from 'node:crypto';

export function offlineUuid(name) {
  const h = createHash('md5').update(`OfflinePlayer:${name}`).digest();
  h[6] = (h[6] & 0x0f) | 0x30;
  h[8] = (h[8] & 0x3f) | 0x80;
  const x = h.toString('hex');
  return `${x.slice(0, 8)}-${x.slice(8, 12)}-${x.slice(12, 16)}-${x.slice(16, 20)}-${x.slice(20)}`;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const names = process.argv.slice(2);
  if (!names.length) {
    console.error('使い方：node src/whitelist.js 名前 [名前 …]');
    process.exit(2);
  }
  console.log(JSON.stringify(names.map((name) => ({ uuid: offlineUuid(name), name })), null, 2));
}
