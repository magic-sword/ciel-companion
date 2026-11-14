import { Vec3 } from 'vec3';
import * as skills from './skills.js';
import * as world from './world.js';
import { within } from './deadline.js';
import { Blueprint } from '../tasks/construction_tasks.js';

/**
 * Bring a region of the world to a blueprint: the construction-task Blueprint format
 * ({levels: [{level, coordinates: [x, y, z], placement: rows of block names}]}), with "" or null
 * for cells that may hold anything. The world is compared with Blueprint.check, so the cells
 * still to change are always read from the world. Besides placing and breaking blocks, a cell
 * may ask for farmland (tilled with a hoe), water (poured from a bucket) or a crop (sown on the
 * farmland below it). A blueprint may also say which blocks count as its block (same(expected,
 * actual)), such as grass for dirt or a wall torch for a torch.
 */

// Crops a blueprint may ask for, the item that plants each, and the blocks that drop it.
export const CROPS = {
    wheat: { seed: 'wheat_seeds', from: ['short_grass', 'tall_grass'] },
};
const TILLABLE = new Set(['grass_block', 'dirt', 'farmland']);
const EMPTY = new Set(['air', 'cave_air', 'short_grass', 'tall_grass', 'fern', 'large_fern', 'snow', 'dead_bush']);
const SPECIAL = new Set(['air', 'farmland', 'water', ...Object.keys(CROPS)]);
const CELL_SECONDS = 15;

const same = (blueprint, expected, actual) => actual === expected || Boolean(blueprint.same?.(expected, actual));

export function remaining(blueprint, bot) {
    return new Blueprint(blueprint).check(bot).mismatches.filter(cell => cell.expected && !same(blueprint, cell.expected, cell.actual));
}

/** A pickaxe when a cell to clear or replace holds a block only a pickaxe breaks well (stone), else null. */
export function clearingTool(blueprint, bot) {
    const hard = remaining(blueprint, bot).some(({ actual }) =>
        !EMPTY.has(actual) && /pickaxe/.test(bot.registry.blocksByName[actual]?.material ?? ''));
    return hard ? 'wooden_pickaxe' : null;
}

/** Items the remaining cells will use up. */
export function materials(blueprint, bot) {
    const need = {};
    const add = (item, n = 1) => { need[item] = (need[item] || 0) + n; };
    for (const cell of remaining(blueprint, bot)) {
        const { expected, actual } = cell;
        if (expected === 'farmland') { if (!TILLABLE.has(actual)) add('dirt'); }
        else if (expected === 'water') add('water_bucket', 0);
        else if (CROPS[expected]) add(CROPS[expected].seed);
        else if (expected !== 'air') add(expected, /_(door|bed)$/.test(expected) ? 0.5 : 1);
    }
    for (const item in need) need[item] = Math.ceil(need[item]);
    if ('water_bucket' in need) need.water_bucket = 1;
    return need;
}

export function seconds(blueprint, bot) {
    return 20 + 6 * remaining(blueprint, bot).length;
}

/**
 * Change the remaining cells in order: clear what is in the way (top down), place blocks
 * (bottom up), pour water, till and sow, then sow what is left. Each cell has its own time.
 * @returns {Promise<boolean>} true when the region matches the blueprint.
 */
export async function buildRegion(bot, blueprint, { passes = 2 } = {}) {
    const index = new Map();
    for (const level of blueprint.levels) {
        level.placement.forEach((row, dz) => row.forEach((name, dx) => {
            if (name) index.set(`${level.coordinates[0] + dx},${level.coordinates[1]},${level.coordinates[2] + dz}`, name);
        }));
    }
    const expectedAt = (x, y, z) => index.get(`${x},${y},${z}`);
    await approach(bot, blueprint);
    for (let pass = 0; pass < passes; pass++) {
        for (const phase of PHASES) {
            const cells = remaining(blueprint, bot).filter(cell => phase.wants(cell)).sort(phase.order);
            for (const cell of cells) {
                if (bot.interrupt_code) return false;
                const [x, y, z] = cell.coordinates;
                const current = bot.blockAt(new Vec3(x, y, z))?.name ?? 'air';
                if (same(blueprint, cell.expected, current) || !phase.wants({ ...cell, actual: current })) continue;
                await within(bot, () => phase.act(bot, x, y, z, cell.expected, expectedAt), CELL_SECONDS,
                    `${phase.name} at ${x}, ${y}, ${z}`);
            }
        }
        const left = remaining(blueprint, bot);
        if (left.length === 0) {
            skills.log(bot, 'The region matches the plan.');
            return true;
        }
        if (pass === passes - 1)
            skills.log(bot, `${left.length} cells still differ from the plan, for example ${describe(left[0])}.`);
    }
    return false;
}

// Walk to the region first when it is far (after fetching materials, say), so the first
// cells do not spend their own time on the walk.
async function approach(bot, blueprint) {
    const first = blueprint.levels[0];
    const centre = new Vec3(first.coordinates[0] + first.placement[0].length / 2, first.coordinates[1],
        first.coordinates[2] + first.placement.length / 2);
    const distance = bot.entity.position.distanceTo(centre);
    if (distance > 12)
        await within(bot, () => skills.goToPosition(bot, centre.x, centre.y, centre.z, 4), 10 + distance / 3, 'walk to the region');
}

/**
 * A bed fills two cells and points the way the bot faces: stand behind the foot, facing the
 * head, and place it on the block under the foot.
 */
async function placeBed(bot, item, cell, partner) {
    const ends = [[cell, partner], [partner, cell]].map(([foot, head]) => ({ foot, head, stand: foot.minus(head.minus(foot)) }));
    const free = p => ['air', 'cave_air'].includes(bot.blockAt(p)?.name) && ['air', 'cave_air'].includes(bot.blockAt(p.offset(0, 1, 0))?.name);
    const { foot, stand } = ends.find(end => free(end.stand)) ?? ends[0];
    const bed = bot.inventory.items().find(i => i.name === item);
    if (!bed) {
        skills.log(bot, `Don't have any ${item} to place.`);
        return false;
    }
    await skills.goToPosition(bot, stand.x, stand.y, stand.z, 0);
    await bot.equip(bed, 'hand');
    await bot.lookAt(foot.offset(0.5, 0, 0.5), true);
    try {
        await bot.placeBlock(bot.blockAt(foot.offset(0, -1, 0)), new Vec3(0, 1, 0));
    } catch (err) {
        // The placement event can time out although the bed was placed; the cell check decides.
    }
    return bot.blockAt(foot)?.name === item;
}

function describe({ coordinates: [x, y, z], expected, actual }) {
    return `${actual} instead of ${expected} at ${x}, ${y}, ${z}`;
}

const top = (a, b) => b.coordinates[1] - a.coordinates[1];
const bottom = (a, b) => a.coordinates[1] - b.coordinates[1];
const solid = name => !SPECIAL.has(name);

const PHASES = [
    {
        name: 'clear',
        wants: ({ expected, actual }) => !EMPTY.has(actual) && actual !== expected
            && !(expected === 'farmland' && TILLABLE.has(actual)) && !solid(expected),
        order: top,
        act: (bot, x, y, z) => skills.breakBlockAt(bot, x, y, z),
    },
    {
        name: 'place',
        wants: ({ expected, actual }) => (solid(expected) && actual !== expected)
            || (expected === 'farmland' && !TILLABLE.has(actual)),
        order: bottom,
        act: (bot, x, y, z, expected, expectedAt) => {
            if (/_bed$/.test(expected)) {
                const here = new Vec3(x, y, z);
                const partner = [[1, 0], [-1, 0], [0, 1], [0, -1]].map(([dx, dz]) => here.offset(dx, 0, dz))
                    .find(p => expectedAt(p.x, p.y, p.z) === expected);
                if (partner) return placeBed(bot, expected, here, partner);
            }
            return skills.placeBlock(bot, expected === 'farmland' ? 'dirt' : expected, x, y, z);
        },
    },
    {
        name: 'pour water',
        wants: ({ expected, actual }) => expected === 'water' && actual !== 'water',
        order: bottom,
        act: async (bot, x, y, z) => {
            if (!world.getInventoryCounts(bot).water_bucket) await skills.useToolOn(bot, 'bucket', 'water');
            await skills.placeBlock(bot, 'water', x, y, z);
        },
    },
    {
        // Sow right after tilling, so walking over bare farmland cannot trample it first.
        name: 'till',
        wants: ({ expected, actual }) => expected === 'farmland' && actual !== 'farmland' && TILLABLE.has(actual),
        order: bottom,
        act: (bot, x, y, z, expected, expectedAt) => {
            const crop = CROPS[expectedAt(x, y + 1, z)];
            const seed = crop && world.getInventoryCounts(bot)[crop.seed] ? crop.seed : null;
            return skills.tillAndSow(bot, x, y, z, seed);
        },
    },
    {
        name: 'sow',
        wants: ({ expected, actual }) => Boolean(CROPS[expected]) && actual !== expected,
        order: bottom,
        act: (bot, x, y, z, expected) => skills.tillAndSow(bot, x, y - 1, z, CROPS[expected].seed),
    },
];
