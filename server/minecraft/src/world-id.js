// ワールドの識別。会話サーバーは、ゲームの場所の記憶をワールドごとに分ける（agent/recall.py）。
// 体のデータ（CIEL_BODY_DATA。拠点の記録と同じ所）に、サーバーごとに 1 つ作って残す。ワールドを作り直すとき
// （scripts/server/reset-minecraft-world.sh）は体のデータも退避するので、新しいワールドには新しい識別が付く。
import fs from 'fs';
import path from 'path';
import { randomUUID } from 'node:crypto';

export function worldId(dataDir, host, port) {
  if (!dataDir) return null;
  const file = path.join(dataDir, `world-${String(host ?? 'local').replace(/[^\w.-]/g, '_')}-${port ?? '25565'}.id`);
  try {
    if (fs.existsSync(file)) {
      const id = fs.readFileSync(file, 'utf8').trim();
      if (/^[\w-]{8,64}$/.test(id)) return id;
    }
    fs.mkdirSync(dataDir, { recursive: true });
    const id = randomUUID();
    fs.writeFileSync(file, id);
    return id;
  } catch (err) {
    console.warn('Could not keep the world id:', err.message);
    return null;
  }
}
