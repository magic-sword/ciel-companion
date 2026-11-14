import { Vec3 } from 'vec3';
import * as skills from './skills.js';
import * as world from './world.js';
import { within } from './deadline.js';
import { MOBS, WOOL_COLORS } from './mobs.js';

const RANGE = 64;
// Looking for a mob that is not in sight: walk legs toward the ground the mob spawns on, each
// to a spot at least LEG / 2 blocks from where the bot has been (LEG blocks along open land
// when no such ground is in sight), with its own time.
const LEG = 32;
const LEGS = 6;
const LEG_SECONDS = 30;
export const EXPLORE_SECONDS = LEGS * LEG_SECONDS;
// A sheared sheep grows its wool back after eating grass, usually within a minute.
const REGROW_WAIT_MS = 30000;

// Upstream entity metadata, by the key names minecraft-data lists for this version.
function metadata(bot, entity, key) {
    const index = bot.registry.entitiesByName[entity.name]?.metadataKeys?.indexOf(key) ?? -1;
    return index === -1 ? undefined : entity.metadata?.[index];
}

/** A mob someone named is treated as theirs and is never killed or sheared. */
export function owned(bot, entity) {
    const name = metadata(bot, entity, 'custom_name');
    return Boolean(name && (typeof name !== 'object' || Object.keys(name).length > 0));
}

/** Whether this mob can give the item by the method now: adult, not someone's, the right colour, not sheared. */
export function suitable(bot, entity, { mob, method, color }) {
    if (entity.name !== mob || owned(bot, entity) || metadata(bot, entity, 'baby') === true) return false;
    if (mob === 'sheep') {
        const wool = Number(metadata(bot, entity, 'wool') ?? 0);
        if (color && WOOL_COLORS[wool & 0x0f] !== color) return false;
        if (method === 'shear' && (wool & 0x10)) return false;
    }
    return true;
}

export function countSuitable(bot, way) {
    return world.getNearbyEntities(bot, RANGE).filter(e => suitable(bot, e, way)).length;
}

/**
 * Get an item from one mob: find the nearest suitable one within range, then kill it or shear
 * it, and pick up what it drops. The caller checks the inventory and repeats.
 */
export async function getFromMob(bot, way) {
    const find = () => world.getNearestEntityWhere(bot, e => suitable(bot, e, way), RANGE);
    let target = find();
    if (!target && !world.getNearestEntityWhere(bot, e => e.name === way.mob && !owned(bot, e), RANGE)) {
        await explore(bot, way.mob, find);
        target = find();
    }
    const kept = MOBS[way.mob]?.methods[way.method]?.stays;
    if (!target && kept && world.getNearestEntityWhere(bot, e => e.name === way.mob && !owned(bot, e), RANGE)) {
        skills.log(bot, `Waiting for a ${way.mob} to be ready to ${way.method} again.`);
        for (const until = Date.now() + REGROW_WAIT_MS; !target && Date.now() < until && !bot.interrupt_code;) {
            await new Promise(resolve => setTimeout(resolve, 1000));
            target = find();
        }
    }
    if (!target) {
        const any = world.getNearestEntityWhere(bot, e => e.name === way.mob, RANGE);
        const note = MOBS[way.mob]?.methods[way.method]?.note;
        skills.log(bot, any
            ? `No ${way.mob} within ${RANGE} blocks can give ${way.item} by ${way.method} now.${note ? ' ' + note : ''}`
            : `No ${way.mob} within ${RANGE} blocks. ${MOBS[way.mob]?.spawn.note ?? ''}`.trim());
        return false;
    }
    if (way.method === 'kill')
        return await skills.attackEntity(bot, target, true);
    const p = target.position;
    if (bot.entity.position.distanceTo(p) > 3)
        await skills.goToPosition(bot, p.x, p.y, p.z, 2);
    if (!await skills.equip(bot, way.tool)) return false;
    await bot.lookAt(target.position.offset(0, target.height / 2, 0));
    await bot.useOn(target);
    await new Promise(resolve => setTimeout(resolve, 500));
    await skills.pickupNearbyItems(bot);
    return true;
}

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

/**
 * Choose where to look next. The mob's spawn ground in sight (within RANGE, with room to stand
 * on it) comes first: of the spots not near a place already visited, the one that is near the
 * bot and leads away from where the search began, so the search keeps going outward. With none
 * in sight, follow the surface along each heading until it is cut off and take the open heading
 * that reaches farthest within a leg, again away from places visited.
 * @returns {{heading, target: Vec3, ground: boolean} | null}
 */
export function nextLeg(bot, ground, visited) {
    const from = bot.entity.position.floored();
    const start = visited[0];
    const fresh = p => visited.every(v => v.distanceTo(p) >= LEG / 2);
    const spots = bot.findBlocks({ matching: block => block?.name === ground, maxDistance: RANGE, count: 4096 })
        .map(p => new Vec3(p.x, p.y + 1, p.z))
        .filter(p => fresh(p) && surface(bot, p.x, p.z, p.y)?.y === p.y);
    if (spots.length > 0) {
        const cost = p => p.distanceTo(from) - 0.5 * p.distanceTo(start);
        const target = spots.reduce((a, b) => cost(b) < cost(a) ? b : a);
        return { heading: heading(target.x - from.x, target.z - from.z), target, ground: true };
    }
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

/** Walk legs toward the mob's spawn ground until found() sees one, or no new heading is left. */
export async function explore(bot, mob, found) {
    const ground = MOBS[mob]?.spawn.ground ?? 'grass_block';
    const visited = [bot.entity.position.floored()];
    for (let leg = 0; leg < LEGS && !bot.interrupt_code; leg++) {
        if (found()) return true;
        const next = nextLeg(bot, ground, visited);
        if (!next) {
            skills.log(bot, `No ${mob} within ${RANGE} blocks and no new way to look.`);
            return false;
        }
        skills.log(bot, `No ${mob} within ${RANGE} blocks; looking ${next.heading}, toward ${next.ground ? ground : 'open land'}.`);
        const { x, y, z } = next.target;
        await within(bot, () => skills.goToPosition(bot, x, y, z, 3), LEG_SECONDS, `walk ${next.heading}`);
        visited.push(bot.entity.position.floored());
    }
    return Boolean(found());
}
