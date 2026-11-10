// Locator Barの通知だけを手掛かりにする。任意のサーバー座標照会は行わない。
// 形式: minecraft-data (1.21.11) packet_tracked_waypoint。
export class PlayerLocator {
  constructor(bot) {
    this.bot = bot;
    this.waypoints = new Map();
    this.receive = packet => {
      const w = packet.waypoint;
      if (!w?.hasUUID || typeof w.uuid !== 'string') return;
      const id = w.uuid.toLowerCase();
      this.waypoints.delete(id);
      if (!['track', 'update'].includes(packet.operation)) return;
      const d = w.data;
      const valid = w.type === 'azimuth' ? Number.isFinite(d)
        : w.type === 'vec3i' ? [d?.x, d?.y, d?.z].every(Number.isFinite)
          : w.type === 'chunk' && [d?.chunkX, d?.chunkZ].every(Number.isInteger);
      if (!valid) return;
      this.waypoints.set(id, { type: w.type, data: typeof d === 'object' ? { ...d } : d });
      while (this.waypoints.size > 256) this.waypoints.delete(this.waypoints.keys().next().value);
    };
    this.clear = () => this.waypoints.clear();
    this.left = player => { if (player.uuid) this.waypoints.delete(player.uuid.toLowerCase()); };
    bot._client.on('tracked_waypoint', this.receive);
    bot.on('respawn', this.clear);
    bot.on('death', this.clear);
    bot.on('playerLeft', this.left);
    bot.once('end', () => this.close());
  }

  hint(name) {
    const uuid = this.bot.players[name]?.uuid;
    if (!uuid) return null; // 色や一覧の順序から持ち主を推測しない。
    const w = this.waypoints.get(uuid.toLowerCase());
    // 静止中は更新通知が来ない。有効性は経過時間でなくuntrackと接続・世界の寿命に従う。
    if (!w) return null;
    const p = this.bot.entity?.position;
    if (!p) return null;
    if (w.type === 'vec3i') return { x: w.data.x, z: w.data.z, source: w.type };
    if (w.type === 'chunk') return { x: w.data.chunkX * 16 + 8, z: w.data.chunkZ * 16 + 8, source: w.type };
    // 公式1.21.11 WaypointTransmitter.EntityAzimuthConnection:
    // (receiver - source).rotateClockwise90()のatan2(z,x)。Javaのyawと同じ（南=0、東=-π/2）。
    return { x: p.x - Math.sin(w.data) * 16, z: p.z + Math.cos(w.data) * 16, angle: w.data, source: w.type };
  }

  close() {
    this.clear();
    this.bot._client.removeListener('tracked_waypoint', this.receive);
    this.bot.removeListener('respawn', this.clear);
    this.bot.removeListener('death', this.clear);
    this.bot.removeListener('playerLeft', this.left);
  }
}
