import { Vec3 } from 'vec3';
import * as skills from './skills.js';
import * as world from './world.js';
import { within } from './deadline.js';
import { explore, nextLeg, EXPLORE_LEGS } from './search.js';
import { MOBS, WOOL_COLORS } from './mobs.js';

const RANGE = 64;
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
// Minecraft time of day in ticks (20 a second): hostile mobs come out on the surface from dusk
// (13000) to dawn (23000).
const NIGHT = [13000, 23000];

/** Seconds until a mob that comes out at night can appear; 0 when it is night or any time suits it. */
export function untilSpawn(bot, mob) {
    if (MOBS[mob]?.spawn.time !== 'night') return 0;
    const t = ((bot.time?.timeOfDay ?? 0) % 24000 + 24000) % 24000;
    return t >= NIGHT[0] && t < NIGHT[1] ? 0 : Math.ceil(((NIGHT[0] - t + 24000) % 24000) / 20);
}

/** A hostile mob never appears on peaceful difficulty: a rule of the game, not a matter of looking. */
export const neverSpawns = (bot, mob) => Boolean(MOBS[mob]?.hostile) && bot.game?.difficulty === 'peaceful';

export async function getFromMob(bot, way) {
    const find = () => world.getNearestEntityWhere(bot, e => suitable(bot, e, way), RANGE);
    let target = find();
    if (!target && neverSpawns(bot, way.mob)) {
        skills.log(bot, `No ${way.mob} appears on peaceful difficulty.`);
        return false;
    }
    // A mob of the night is waited for, then looked for.
    const wait = target ? 0 : untilSpawn(bot, way.mob);
    if (wait > 0) {
        skills.log(bot, `Waiting about ${wait}s for night, when ${way.mob}s come out.`);
        while (untilSpawn(bot, way.mob) > 0 && !bot.interrupt_code) await new Promise(resolve => setTimeout(resolve, 1000));
        target = find();
    }
    if (!target && !world.getNearestEntityWhere(bot, e => e.name === way.mob && !owned(bot, e), RANGE)) {
        await explore(bot, way.mob, find, MOBS[way.mob]?.spawn.ground ?? null);
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

// The search is shared with blocks (search.js); kept here under the names callers know.
export { nextLeg, EXPLORE_LEGS };
