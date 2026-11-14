import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as skills from './skills.js';
import { runPlan, haveStep } from './plan.js';
import { buildRegion, clearingTool, materials, remaining, seconds } from './region.js';
import { findSites, atSite } from './sites.js';
import { getTypeOfGeneric, blockSatisfied } from '../npc/utils.js';

/**
 * Houses from the upstream NPC building plans (src/agent/npc/construction/*.json): levels of
 * rows (z) of cells (x) with generic names such as "planks", "door" or "bed", "" for cells that
 * may hold anything, and an offset for how many levels go below the ground. The executor turns
 * one into a region blueprint at a site and builds it with the region executor; every block and
 * item it needs, the bed included, is a "have" step before it.
 */
const PLANS = path.join(path.dirname(fileURLToPath(import.meta.url)), '../npc/construction');
const PICKAXES = ['wooden_pickaxe', 'stone_pickaxe', 'copper_pickaxe', 'iron_pickaxe', 'golden_pickaxe', 'diamond_pickaxe', 'netherite_pickaxe'];

export function houseNames() {
    return fs.readdirSync(PLANS).filter(file => file.endsWith('.json')).map(file => file.slice(0, -5)).sort();
}

export function loadHouse(name) {
    return houseNames().includes(name) ? JSON.parse(fs.readFileSync(path.join(PLANS, `${name}.json`), 'utf8')) : null;
}

/** Turn a level (rows of z, cells of x) a quarter turn, turns times. */
export function rotate(rows, turns) {
    let grid = rows;
    for (let i = 0; i < ((turns % 4) + 4) % 4; i++)
        grid = grid[0].map((_, x) => grid.map(row => row[x]).reverse());
    return grid;
}

/** The [width (x), depth (z)] a house takes, turned. */
export function footprint(house, turns = 0) {
    const level = rotate(house.blocks[0], turns);
    return [level[0].length, level.length];
}

/**
 * The region blueprint of a house whose lowest ground-level corner is corner (the ground block):
 * level 0 of the plan is house.offset levels from the block above the ground. Generic names
 * become this bot's blocks (its most common wood, its wool colour for the bed) as upstream does.
 */
export function houseBlueprint(bot, house, corner, turns = 0) {
    const generic = {};
    const name = cell => {
        if (!cell) return '';
        const block = getTypeOfGeneric(bot, cell);
        generic[block] = cell;
        return block;
    };
    return {
        levels: house.blocks.map((rows, i) => ({
            level: i,
            coordinates: [corner.x, corner.y + 1 + house.offset + i, corner.z],
            placement: rotate(rows, turns).map(row => row.map(name)),
        })),
        same: (expected, actual) => generic[expected] !== undefined && blockSatisfied(generic[expected], { name: actual }),
    };
}

/** Tools for the ground in the way, every block and item the house still needs, then the house. */
export function houseSteps(blueprint, bot) {
    const need = item => b => materials(blueprint, b)[item] || 0;
    const steps = [haveStep('pickaxe', 'wooden_pickaxe', b => clearingTool(blueprint, b) ? 1 : 0, { satisfiedBy: PICKAXES })];
    for (const item of Object.keys(materials(blueprint, bot)).sort())
        steps.push(haveStep(item, item, need(item)));
    steps.push({
        id: 'house', label: 'clear the place and build the house', needs: steps.map(step => step.id),
        done: b => remaining(blueprint, b).length === 0,
        run: b => buildRegion(b, blueprint),
        seconds: b => seconds(blueprint, b),
    });
    return steps;
}

/**
 * Build a house from a plan near the bot. A flat place of grass or dirt is chosen as for farms;
 * the house is turned to fit it.
 */
export async function buildHouse(agent, name) {
    const bot = agent.bot;
    const house = loadHouse(name);
    if (!house) {
        skills.log(bot, `There is no house plan named ${name}; known plans: ${houseNames().join(', ')}.`);
        return false;
    }
    // A house begun and not finished is carried on where it stands, wherever the bot is now.
    const begun = bot.houses?.[name];
    if (begun && remaining(houseBlueprint(bot, house, begun.corner, begun.turns), bot).length > 0)
        return await houseAt(bot, house, name, begun);
    const sites = [0, 1].flatMap(turns => {
        const [width, depth] = footprint(house, turns);
        return findSites(bot, width, depth).map(site => ({ ...site, turns }));
    }).sort((a, b) => (a.changes + 0.1 * a.distance) - (b.changes + 0.1 * b.distance)).slice(0, 3)
        .map((site, i) => ({ ...site, id: `site_${i + 1}` }));
    if (sites.length === 0) {
        const [width, depth] = footprint(house);
        skills.log(bot, `There is no grass or dirt place for the ${width} x ${depth} ${name} within 24 blocks.`);
        return false;
    }
    const [width, depth] = footprint(house);
    return await atSite(bot, sites, width + depth, `the ${name}`, site => houseAt(bot, house, name, site));
}

async function houseAt(bot, house, name, site) {
    skills.log(bot, `Building the ${name} at ${site.corner.x}, ${site.corner.y}, ${site.corner.z}.`);
    bot.houses = { ...(bot.houses ?? {}), [name]: site };
    const blueprint = houseBlueprint(bot, house, site.corner, site.turns);
    reserve(bot, blueprint);
    return await runPlan(bot, houseSteps(blueprint, bot));
}

// The house's own place is not dug up for materials, while it is built or after.
function reserve(bot, blueprint) {
    const levels = blueprint.levels;
    const [x, y, z] = levels[0].coordinates;
    const box = { min: [x, y, z], max: [x + levels[0].placement[0].length - 1, levels[levels.length - 1].coordinates[1], z + levels[0].placement.length - 1] };
    bot.reserved = [...(bot.reserved ?? []).filter(other => JSON.stringify(other) !== JSON.stringify(box)), box];
}
