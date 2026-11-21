import { Vec3 } from 'vec3';
import * as skills from './skills.js';
import * as world from './world.js';
import { base } from './base.js';
import { within } from './deadline.js';
import { expected, limit } from './estimate.js';
import { runPlan, haveStep, dropStep, fillBucketStep } from './plan.js';
import { CROPS, buildRegion, materials, remaining, seconds, estimate } from './region.js';
import { findSites, atSite } from './sites.js';

const CELL_SECONDS = limit('cell');
const HOES = ['wooden_hoe', 'stone_hoe', 'copper_hoe', 'iron_hoe', 'golden_hoe', 'diamond_hoe', 'netherite_hoe'];

/**
 * A square farm: farmland with one water block in the middle (farmland stays wet within four
 * blocks of water, so up to 9 x 9), the crop on top, and room above it.
 */
export function farmBlueprint(corner, size, crop = 'wheat') {
    const middle = Math.floor(size / 2);
    const layer = (fill, centre) => Array.from({ length: size }, (_, z) =>
        Array.from({ length: size }, (_, x) => x === middle && z === middle ? centre : fill));
    const at = dy => [corner.x, corner.y + dy, corner.z];
    return {
        levels: [
            { level: 0, coordinates: at(0), placement: layer('farmland', 'water') },
            { level: 1, coordinates: at(1), placement: layer(crop, 'air') },
            { level: 2, coordinates: at(2), placement: layer('air', 'air') },
        ],
    };
}

/** The steps that turn the place into the farm: tools and materials first, then the region. */
export function farmSteps(blueprint, crop = 'wheat') {
    const need = item => bot => materials(blueprint, bot)[item] || 0;
    const wantsWater = bot => 'water_bucket' in materials(blueprint, bot);
    const tilling = bot => remaining(blueprint, bot).some(c => c.expected === 'farmland' || CROPS[c.expected]) ? 1 : 0;
    const { seed, from } = CROPS[crop];
    const steps = [
        haveStep('hoe', 'wooden_hoe', tilling, { satisfiedBy: HOES }),
        dropStep('seeds', seed, need(seed), from),
        haveStep('bucket', 'bucket', bot => wantsWater(bot) ? 1 : 0, { satisfiedBy: ['bucket', 'water_bucket'] }),
        fillBucketStep('water', wantsWater, { needs: ['bucket'] }),
        haveStep('dirt', 'dirt', need('dirt')),
    ];
    steps.push({
        id: 'farm', kind: 'build', label: 'clear, level, water, till and sow the farm', subject: 'farm', needs: steps.map(step => step.id),
        done: bot => remaining(blueprint, bot).length === 0,
        run: bot => buildRegion(bot, blueprint),
        seconds: bot => seconds(blueprint, bot),
        estimate: bot => estimate(blueprint, bot),
    });
    return steps;
}

// A place that needs more blocks moved than this is a real change to the land, so the model
// chooses (and may ask the owner) instead of the executor.
const levelingLimit = size => size;

/**
 * Make a farm near the bot. The executor picks the place when one is clearly fine; otherwise
 * it reports the places and waits for !chooseOption.
 */
export async function makeFarm(agent, size, crop = 'wheat') {
    const bot = agent.bot;
    if (!CROPS[crop]) {
        skills.log(bot, `Cannot farm ${crop}; known crops: ${Object.keys(CROPS).join(', ')}.`);
        return false;
    }
    const sites = findSites(bot, size, size);
    if (sites.length === 0) {
        skills.log(bot, `There is no grass or dirt place for a ${size} x ${size} farm within 24 blocks.`);
        return false;
    }
    return await atSite(bot, sites, levelingLimit(size), `the ${size} x ${size} farm`, site => farmAt(bot, site, size, crop));
}

async function farmAt(bot, site, size, crop) {
    skills.log(bot, `Making the farm at ${site.corner.x}, ${site.corner.y}, ${site.corner.z}.`);
    return await runPlan(bot, farmSteps(farmBlueprint(site.corner, size, crop), crop), { title: `${crop} farm ${size}x${size}` });
}

// How far around the bot (or the base) sowing looks for farmland.
export const SOW_RADIUS = 16;
const TILLABLE = ['grass_block', 'dirt'];
const open = (bot, p) => bot.blockAt(p.offset(0, 1, 0))?.name === 'air';
const byDistance = from => (a, b) => a.distanceTo(from) - b.distanceTo(from);

/** Farmland with nothing growing on it near a point (the bot by default), nearest first. */
export function emptyFarmland(bot, { point = bot.entity.position, radius = SOW_RADIUS } = {}) {
    return bot.findBlocks({ matching: b => b?.name === 'farmland', maxDistance: radius, count: 256, point })
        .filter(p => open(bot, p)).sort(byDistance(point));
}

/**
 * Grass or dirt near the bot that could be tilled: open above, near water first (farmland
 * within four blocks of water stays wet), then nearest.
 */
export function tillableGround(bot, { radius = 8 } = {}) {
    const here = bot.entity.position;
    const water = bot.findBlocks({ matching: b => b?.name === 'water', maxDistance: radius + 4, count: 64 });
    const wet = p => water.some(w => w.y === p.y && Math.abs(w.x - p.x) <= 4 && Math.abs(w.z - p.z) <= 4);
    return bot.findBlocks({ matching: b => TILLABLE.includes(b?.name), maxDistance: radius, count: 256 })
        .filter(p => open(bot, p))
        .sort((a, b) => (wet(b) - wet(a)) || a.distanceTo(here) - b.distanceTo(here));
}

const cellKey = p => `${p.x},${p.y},${p.z}`;

/**
 * The steps that plant the crop on the given cells: seeds first, then the cells still to till
 * (with a hoe) and to sow. Each cell is read from the world, so a cell planted by someone else
 * is skipped and one trampled back to dirt is tilled again.
 */
export function sowSteps(cells, crop = 'wheat', { tilling = false } = {}) {
    const { seed, from } = CROPS[crop];
    const name = (bot, p) => bot.blockAt(p)?.name;
    const untilled = bot => tilling ? cells.filter(p => TILLABLE.includes(name(bot, p)) && open(bot, p)) : [];
    const bare = bot => cells.filter(p => name(bot, p) === 'farmland' && open(bot, p));
    // Seeds for the farmland still bare and the ground still to till.
    const steps = [dropStep('seeds', seed, bot => bare(bot).length + untilled(bot).length, from)];
    const needs = ['seeds'];
    if (tilling) {
        steps.unshift(haveStep('hoe', 'wooden_hoe', bot => untilled(bot).length ? 1 : 0, { satisfiedBy: HOES }));
        steps.push({
            id: 'till', kind: 'do', label: `till ${cells.length} cells`, subject: 'farmland', needs: ['hoe'],
            done: bot => untilled(bot).length === 0,
            run: async bot => {
                for (const p of untilled(bot)) {
                    if (bot.interrupt_code) return;
                    await within(bot, () => skills.till(bot, p.x, p.y, p.z), CELL_SECONDS, `till at ${cellKey(p)}`);
                }
            },
            seconds: bot => 20 + CELL_SECONDS * untilled(bot).length,
            estimate: bot => untilled(bot).length * expected('cell', 'till'),
        });
        needs.push('till');
    }
    steps.push({
        id: 'sow', kind: 'do', label: `sow ${seed}`, subject: crop, needs,
        // Done when no farmland among the cells is bare (tilling, if any, comes first).
        done: bot => bare(bot).length === 0,
        run: async bot => {
            for (const p of bare(bot)) {
                if (bot.interrupt_code || !(world.getInventoryCounts(bot)[seed] > 0)) return;
                await within(bot, () => skills.sow(bot, p.x, p.y, p.z, seed), CELL_SECONDS, `sow at ${cellKey(p)}`);
            }
        },
        seconds: bot => 20 + CELL_SECONDS * bare(bot).length,
        estimate: bot => bare(bot).length * expected('cell', 'sow'),
    });
    return steps;
}

/**
 * Sow up to num cells of farmland near the bot. Without empty farmland near, it lists what can
 * be done instead (till the ground here, go back to the farm at the base) and waits for
 * !chooseOption; a new watered farm is !buildFarm.
 */
export async function sowFarmland(agent, num, crop = 'wheat') {
    const bot = agent.bot;
    if (!CROPS[crop]) {
        skills.log(bot, `Cannot sow ${crop}; known crops: ${Object.keys(CROPS).join(', ')}.`);
        return false;
    }
    const cells = emptyFarmland(bot).slice(0, num);
    if (cells.length > 0) {
        skills.log(bot, `Sowing ${cells.length} cells of farmland.`);
        return await runPlan(bot, sowSteps(cells, crop), { title: `sow ${crop}` });
    }
    const options = {};
    const lines = [];
    const home = base(bot)?.home;
    if (home) {
        const at = new Vec3(home[0], home[1], home[2]);
        const far = bot.entity.position.distanceTo(at) > SOW_RADIUS / 2;
        if (far && emptyFarmland(bot, { point: at }).length > 0) {
            options.base_farm = async () => {
                await skills.goToPosition(bot, at.x, at.y, at.z, 3);
                return await sowFarmland(agent, num, crop);
            };
            lines.push(`base_farm: go back to the base at ${home.join(', ')}, which has empty farmland, and sow there.`);
        }
    }
    const ground = tillableGround(bot).slice(0, num);
    if (ground.length > 0) {
        options.till_here = () => runPlan(bot, sowSteps(ground, crop, { tilling: true }), { title: `till and sow ${crop}` });
        lines.push(`till_here: till ${ground.length} cells of the ground here with a hoe and sow them.`);
    }
    lines.push(`Or make a new farm with water with !buildFarm.`);
    const text = `There is no empty farmland within ${SOW_RADIUS} blocks. Choose with !chooseOption, or ask first:\n${lines.join('\n')}`;
    if (Object.keys(options).length > 0)
        bot.pendingChoice = { question: `where to sow ${crop}`, text, options };
    skills.log(bot, text);
    return false;
}
