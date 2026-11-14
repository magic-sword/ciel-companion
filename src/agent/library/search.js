import { Vec3 } from 'vec3';
import * as skills from './skills.js';
import * as world from './world.js';
import { within } from './deadline.js';
import { recordTime } from './timing.js';
import { limit } from './estimate.js';

/**
 * Looking for what is not in sight, a mob or a block: walk legs on the surface, each to a spot
 * at least LEG / 2 blocks from where the bot has been, with its own time. An ore not found on
 * the surface is looked for underground: dig down to the depth where it is most common, then
 * tunnel out a leg at a time.
 */
const RANGE = 64;
const LEG = 32;
export const EXPLORE_LEGS = 6;
const LEGS = EXPLORE_LEGS;
const LEG_SECONDS = limit('explore_leg');

// Where each ore is most common (Minecraft 1.21, https://minecraft.wiki/w/Ore).
export const ORE_DEPTH = { coal_ore: 96, copper_ore: 48, iron_ore: 16, lapis_ore: 0, gold_ore: -16,
    redstone_ore: -58, diamond_ore: -58, emerald_ore: 232 };
export const TUNNELS = 4;
const TUNNEL = 16;
const TUNNEL_SECONDS = limit('tunnel_leg');

const HEADINGS = [['east', 1, 0], ['south-east', 1, 1], ['south', 0, 1], ['south-west', -1, 1],
    ['west', -1, 0], ['north-west', -1, -1], ['north', 0, -1], ['north-east', 1, -1]];

// Where one can stand in the column at x, z near height y, with the block under it, or null
// when there is none within reach (a wall, a cliff, or land not loaded).
function surface(bot, x, z, y) {
    for (let dy = 4; dy >= -4; dy--) {
        const ground = bot.blockAt(new Vec3(x, y + dy, z));
        const above = bot.blockAt(new Vec3(x, y + dy + 1, z));
        const head = bot.blockAt(new Vec3(x, y + dy + 2, z));
        if (!ground || !above || !head) return null;
        if (ground.boundingBox === 'block' && above.boundingBox === 'empty' && head.boundingBox === 'empty')
            return { y: y + dy + 1, name: ground.name };
    }
    return null;
}

function heading(dx, dz) {
    const turn = Math.round(Math.atan2(dz, dx) / (Math.PI / 4));
    return HEADINGS[(turn + 8) % 8][0];
}

// Whether the bot could see the top of the block under p: no solid block on the line from its eyes.
function inSight(bot, p) {
    const eye = bot.entity.position.offset(0, 1.62, 0);
    const top = new Vec3(p.x + 0.5, p.y + 0.05, p.z + 0.5);
    const steps = Math.ceil(eye.distanceTo(top) * 2);
    for (let i = 1; i < steps; i++) {
        const at = eye.plus(top.minus(eye).scaled(i / steps)).floored();
        if (at.equals(p.offset(0, -1, 0))) return true;
        if (bot.blockAt(at)?.boundingBox === 'block') return false;
    }
    return true;
}

/**
 * Choose where to look next. The mob's spawn ground in sight (within RANGE, with room to stand
 * on it, and no wall in between) comes first: of the spots not near a place already tried, the
 * one that is near the bot and leads away from where the search began, so the search keeps
 * going outward. With none in sight, follow the surface along each heading until it is cut off
 * and take the open heading that reaches farthest within a leg, again away from places tried.
 * @param visited places reached and targets that could not be reached, the start first.
 * @returns {{heading, target: Vec3, ground: boolean} | null}
 */
export function nextLeg(bot, ground, visited) {
    const from = bot.entity.position.floored();
    const start = visited[0];
    const fresh = p => visited.every(v => v.distanceTo(p) >= LEG / 2);
    const cost = p => p.distanceTo(from) - 0.5 * p.distanceTo(start);
    const spots = !ground ? [] : bot.findBlocks({ matching: block => block?.name === ground, maxDistance: RANGE, count: 4096 })
        .map(p => new Vec3(p.x, p.y + 1, p.z))
        .filter(p => fresh(p) && surface(bot, p.x, p.z, p.y)?.y === p.y)
        .sort((a, b) => cost(a) - cost(b));
    const target = spots.find(p => inSight(bot, p));
    if (target)
        return { heading: heading(target.x - from.x, target.z - from.z), target, ground: true };
    let best = null;
    for (const [name, dx, dz] of HEADINGS) {
        const norm = Math.hypot(dx, dz);
        let y = from.y, reach = null;
        for (let d = 4; d <= LEG; d += 4) {
            const x = Math.round(from.x + dx / norm * d), z = Math.round(from.z + dz / norm * d);
            const s = surface(bot, x, z, y);
            if (!s) break;
            y = s.y;
            reach = new Vec3(x, s.y, z);
        }
        if (!reach || reach.distanceTo(from) < 8 || !fresh(reach)) continue;
        if (!best || reach.distanceTo(from) > best.target.distanceTo(from)) best = { heading: name, target: reach, ground: false };
    }
    return best;
}

/**
 * Walk legs until found() sees what is looked for (a mob, a block), or no new heading is left:
 * toward the ground it is on (a mob's spawn ground) when given and in sight, otherwise along
 * open land. The places tried are kept on the bot for the next search for the same thing (a
 * retry starts where this one ended), and dropped once it is found.
 */
export async function explore(bot, label, found, ground = null) {
    const mob = label;
    bot.searched = bot.searched ?? {};
    const visited = bot.searched[mob] = bot.searched[mob] ?? [bot.entity.position.floored()];
    for (let leg = 0; leg < LEGS && !bot.interrupt_code; leg++) {
        if (found()) {
            delete bot.searched[mob];
            return true;
        }
        const next = nextLeg(bot, ground, visited);
        if (!next) {
            skills.log(bot, `No ${mob} within ${RANGE} blocks and no new way to look.`);
            return false;
        }
        skills.log(bot, `No ${mob} within ${RANGE} blocks; looking ${next.heading}, toward ${next.ground ? ground : 'open land'}.`);
        const { x, y, z } = next.target;
        const began = Date.now(), from = bot.entity.position.clone();
        await within(bot, () => skills.goToPosition(bot, x, y, z, 3), LEG_SECONDS, `walk ${next.heading}`);
        recordTime('explore_leg', began, { blocks: Math.round(from.distanceTo(bot.entity.position)),
            reached: bot.entity.position.distanceTo(next.target) <= 4 });
        // A target not reached is tried too, so a spot behind a wall is not chosen again.
        visited.push(bot.entity.position.floored(), next.target);
    }
    if (!found()) return false;
    delete bot.searched[mob];
    return true;
}

const oreOf = names => names.map(n => n.replace(/^deepslate_/, '')).find(n => ORE_DEPTH[n] !== undefined) ?? null;

/** Whether looking for these blocks goes underground when they are not on the surface. */
export const digsFor = names => oreOf(names) !== null;

/**
 * Look for any of the blocks until one is within RANGE: on the surface first, then, for an
 * ore, underground at its depth. Dug blocks are left as they fall; the caller mines what it found.
 */
export async function searchBlocks(bot, names) {
    const found = () => world.getNearestBlock(bot, names, RANGE) !== null;
    if (found()) return true;
    if (await explore(bot, names[0], found)) return true;
    const ore = oreOf(names);
    if (!ore || bot.interrupt_code) return false;
    const depth = ORE_DEPTH[ore];
    const y = Math.floor(bot.entity.position.y);
    if (y > depth + 2) {
        skills.log(bot, `No ${ore} on the surface; digging down to about y=${depth}, where it is most common.`);
        const began = Date.now();
        await within(bot, () => skills.digDown(bot, y - depth), limit('mine', 'cobblestone', y - depth), 'dig down');
        recordTime('dig_down', began, { blocks: y - Math.floor(bot.entity.position.y) });
    }
    const headings = [[1, 0], [0, 1], [-1, 0], [0, -1]];
    for (let i = 0; i < TUNNELS && !found() && !bot.interrupt_code; i++) {
        const [dx, dz] = headings[i % 4];
        const from = bot.entity.position.floored();
        skills.log(bot, `Tunnelling ${TUNNEL} blocks to look for ${ore}.`);
        const began = Date.now();
        await within(bot, () => skills.goToPosition(bot, from.x + dx * TUNNEL, from.y, from.z + dz * TUNNEL, 1), TUNNEL_SECONDS, 'tunnel');
        recordTime('tunnel_leg', began, { blocks: Math.round(from.distanceTo(bot.entity.position)) });
    }
    return found();
}
