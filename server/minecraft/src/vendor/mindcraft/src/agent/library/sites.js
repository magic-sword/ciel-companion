import { Vec3 } from 'vec3';
import * as skills from './skills.js';

/**
 * Find places for a width x depth plan near the bot. For each column the ground is the
 * highest solid block within a few blocks of the bot's height that has room above it. A place
 * is scored by how many blocks the ground must be raised or lowered to one level, plus a little
 * for distance. Places with water, lava, trees or blocks the bot may not break are left out.
 * @returns {{id, corner: Vec3, size: [number, number], changes, distance}[]} best first, not overlapping.
 */
export function findSites(bot, width, depth, { radius = 24, maxRise = 1, count = 3, ground = GROUND } = {}) {
    const origin = bot.entity.position.floored();
    const columns = new Map();
    const column = (x, z) => {
        const k = `${x},${z}`;
        if (!columns.has(k)) columns.set(k, readColumn(bot, x, z, origin.y, ground));
        return columns.get(k);
    };
    const sites = [];
    for (let x = origin.x - radius; x <= origin.x + radius - width + 1; x++) {
        for (let z = origin.z - radius; z <= origin.z + radius - depth + 1; z++) {
            const heights = [];
            let usable = true;
            for (let dx = 0; dx < width && usable; dx++) for (let dz = 0; dz < depth && usable; dz++) {
                const c = column(x + dx, z + dz);
                if (!c) usable = false; else heights.push(c);
            }
            if (!usable) continue;
            const sorted = heights.map(c => c.y).sort((a, b) => a - b);
            const level = sorted[Math.floor(sorted.length / 2)];
            if (sorted[0] < level - maxRise || sorted[sorted.length - 1] > level + maxRise) continue;
            const changes = sorted.reduce((n, y) => n + Math.abs(y - level), 0);
            const centre = new Vec3(x + width / 2, level + 1, z + depth / 2);
            const distance = centre.distanceTo(bot.entity.position);
            sites.push({ corner: new Vec3(x, level, z), size: [width, depth], changes, distance: Math.round(distance) });
        }
    }
    sites.sort((a, b) => (a.changes + 0.1 * a.distance) - (b.changes + 0.1 * b.distance));
    const chosen = [];
    for (const site of sites) {
        if (chosen.some(other => overlaps(site, other))) continue;
        chosen.push({ id: `site_${chosen.length + 1}`, ...site });
        if (chosen.length === count) break;
    }
    return chosen;
}

const GROUND = new Set(['grass_block', 'dirt', 'coarse_dirt', 'podzol', 'rooted_dirt']);
const LOOSE = /^(air|cave_air|short_grass|tall_grass|fern|large_fern|dandelion|poppy|.*_tulip|azure_bluet|oxeye_daisy|cornflower|allium|blue_orchid|lily_of_the_valley|snow)$/;

function readColumn(bot, x, z, y0, ground) {
    for (let y = y0 + 3; y >= y0 - 4; y--) {
        const block = bot.blockAt(new Vec3(x, y, z));
        if (!block) return null;
        if (LOOSE.test(block.name)) continue;
        if (!ground.has(block.name)) return null;
        for (let up = 1; up <= 2; up++) {
            const above = bot.blockAt(new Vec3(x, y + up, z));
            if (!above || !LOOSE.test(above.name)) return null;
        }
        return { y };
    }
    return null;
}

function overlaps(a, b) {
    return a.corner.x < b.corner.x + b.size[0] && b.corner.x < a.corner.x + a.size[0]
        && a.corner.z < b.corner.z + b.size[1] && b.corner.z < a.corner.z + a.size[1];
}

/** One line per site for the model to choose from. */
export function describeSites(sites) {
    return sites.map(site => `${site.id}: corner ${site.corner.x}, ${site.corner.y}, ${site.corner.z}, `
        + `${site.changes} blocks to level, ${site.distance} blocks away`).join('\n');
}

/**
 * Go on at the best site when it needs at most limit blocks levelled; otherwise list the sites
 * and wait for !chooseOption, since a real change to the land is the model's (or owner's) call.
 */
export async function atSite(bot, sites, limit, what, go) {
    if (sites[0].changes <= limit) return await go(sites[0]);
    bot.pendingChoice = {
        question: `where to make ${what}`,
        options: Object.fromEntries(sites.map(site => [site.id, () => go(site)])),
    };
    skills.log(bot, `Every place needs the land changed. Choose where to make ${what} with !chooseOption, or ask first:
${describeSites(sites)}`);
    return false;
}
