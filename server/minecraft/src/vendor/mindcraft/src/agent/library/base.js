import fs from 'fs';
import path from 'path';
import { Vec3 } from 'vec3';

/**
 * The bot's base: a place it was told (or chose) to treat as home, and the crafting table,
 * furnace and chest kept there. Plans use a base station instead of making a new one when it is
 * within reach, as a player goes back to the table at home. The record is game memory: the host
 * sets bot.baseFile (one file per world) to keep it across restarts; without it, it lasts while
 * the bot is connected. Every station is checked against the world before use, and forgotten
 * when it is no longer there.
 */
export const STATIONS = ['crafting_table', 'furnace', 'chest'];
// How far a base station is worth walking to instead of placing a carried one or making one.
export const BASE_RANGE = 48;
// Stations within this distance of home belong to the base.
export const HOME_RADIUS = 8;

export function base(bot) {
    if (bot.base === undefined) {
        bot.base = null;
        try {
            if (bot.baseFile && fs.existsSync(bot.baseFile)) bot.base = JSON.parse(fs.readFileSync(bot.baseFile, 'utf8'));
        } catch (err) {
            console.warn('Could not read the base:', err.message);
        }
    }
    return bot.base;
}

function save(bot) {
    if (!bot.baseFile) return;
    try {
        fs.mkdirSync(path.dirname(bot.baseFile), { recursive: true });
        fs.writeFileSync(bot.baseFile, JSON.stringify(bot.base));
    } catch (err) {
        console.warn('Could not keep the base:', err.message);
    }
}

const vec = a => new Vec3(a[0], a[1], a[2]);

/** Make the place the bot stands its base, with the stations already within HOME_RADIUS. */
export function setBase(bot) {
    const home = bot.entity.position.floored();
    const stations = {};
    for (const name of STATIONS) {
        const found = bot.findBlocks({ matching: b => b?.name === name, maxDistance: HOME_RADIUS, count: 1 })[0];
        if (found) stations[name] = [found.x, found.y, found.z];
    }
    bot.base = { home: [home.x, home.y, home.z], stations };
    save(bot);
    return bot.base;
}

/** A base station that is still there and within range of the bot, or null. */
export function baseStation(bot, name, range = BASE_RANGE) {
    const at = base(bot)?.stations?.[name];
    if (!at) return null;
    const p = vec(at);
    const block = bot.blockAt(p);
    if (block && block.name !== name) {
        delete bot.base.stations[name];
        save(bot);
        return null;
    }
    return block && bot.entity.position.distanceTo(p) <= range ? p : null;
}

/** Whether a station placed at p is at home, where it is left as the base's own. */
export function atHome(bot, name, p) {
    const b = base(bot);
    if (!b || b.stations?.[name] || vec(b.home).distanceTo(p) > HOME_RADIUS) return false;
    b.stations = { ...(b.stations ?? {}), [name]: [p.x, p.y, p.z] };
    save(bot);
    return true;
}

/** One line for the model: where the base is and what it has. */
export function describeBase(bot) {
    const b = base(bot);
    if (!b) return 'There is no base yet.';
    const kept = Object.keys(b.stations ?? {});
    return `The base is at ${b.home.join(', ')}` + (kept.length ? ` with a ${kept.join(', ')}.` : ' with no crafting table, furnace or chest yet.');
}
