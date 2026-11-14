import * as skills from './skills.js';
import { runPlan, haveStep, dropStep, fillBucketStep } from './plan.js';
import { CROPS, buildRegion, materials, remaining, seconds } from './region.js';
import { findSites, atSite } from './sites.js';

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
        id: 'farm', label: 'clear, level, water, till and sow the farm', needs: steps.map(step => step.id),
        done: bot => remaining(blueprint, bot).length === 0,
        run: bot => buildRegion(bot, blueprint),
        seconds: bot => seconds(blueprint, bot),
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
    return await runPlan(bot, farmSteps(farmBlueprint(site.corner, size, crop), crop));
}
