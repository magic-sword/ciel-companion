// CIEL's world protection boundary. Navigation decisions belong to Mindcraft.
import { NATURAL } from '../movements.js';

const key = p => `${p.x},${p.y},${p.z}`;
export function protectWorld(bot) {
  const placed = new Set(), permitted = new Set();
  const allowed = block => Boolean(block && (NATURAL.test(block.name) || /_ore$/.test(block.name)
    || (block.position && (placed.has(key(block.position)) || permitted.has(key(block.position))))));
  bot.cielCanBreak = allowed;
  const constrain = movements => {
    // Preserve Mindcraft's digging, towers, scaffold choices and cost policy.
    if (!movements.__cielProtection) {
      movements.exclusionAreasBreak.push(block => allowed(block) ? 0 : 100);
      movements.__cielProtection = true;
    }
    return movements;
  };
  for (const method of ['setMovements', 'getPathTo']) {
    const original = bot.pathfinder[method].bind(bot.pathfinder);
    bot.pathfinder[method] = (movements, ...args) => original(constrain(movements), ...args);
  }
  const dig = bot.dig.bind(bot);
  bot.dig = (block, ...args) => {
    if (!allowed(block)) return Promise.reject(new Error('protected_block'));
    return dig(block, ...args);
  };
  const place = bot.placeBlock.bind(bot);
  bot.placeBlock = async (reference, face, ...args) => {
    const result = await place(reference, face, ...args);
    placed.add(key(reference.position.plus(face)));
    return result;
  };
  return {
    async permit(positions, run) {
      for (const p of positions) permitted.add(key(p));
      try { return await run(); }
      finally { for (const p of positions) permitted.delete(key(p)); }
    },
  };
}
