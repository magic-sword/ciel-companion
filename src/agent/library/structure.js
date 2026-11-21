import * as skills from './skills.js';
import { runPlan, haveStep } from './plan.js';
import { buildRegion, materials, remaining, seconds, estimate, clearingTool } from './region.js';

const PICKAXES = ['wooden_pickaxe', 'stone_pickaxe', 'copper_pickaxe', 'iron_pickaxe', 'golden_pickaxe', 'diamond_pickaxe', 'netherite_pickaxe'];
// The most a structure may be on each side, and the most cells it may ask for.
export const MAX_SIDE = 16;
export const MAX_CELLS = 512;
// Symbols every legend has: a cell left as it is, and a cell to clear.
const ANY = '.';
const CLEAR = '_';

/**
 * Read a structure written as a legend and layers into a blueprint (the region executor's format).
 * legend: "c=cobblestone, g=glass" (one symbol per block name). layers: bottom layer first,
 * separated by "/"; each layer is rows separated by ",", each row one symbol per block along +x,
 * the rows along +z. "." leaves a cell as it is and "_" clears it. The corner (x, y, z) is the
 * bottom layer's first symbol of its first row.
 * @returns {{blueprint, cells} | {error: string}}
 */
export function parseStructure(registry, x, y, z, legend, layers) {
    const names = { [ANY]: '', [CLEAR]: 'air' };
    for (const entry of legend.split(',').map(s => s.trim()).filter(Boolean)) {
        const match = entry.match(/^(\S)\s*=\s*([a-z0-9_]+)$/);
        if (!match) return { error: `Cannot read "${entry}" in the legend; write it as symbol=block_name, such as c=cobblestone.` };
        const [, symbol, name] = match;
        if (symbol === ANY || symbol === CLEAR)
            return { error: `"${symbol}" is kept for ${symbol === ANY ? 'a cell left as it is' : 'a cell to clear'}.` };
        if (!registry.blocksByName[name]) return { error: `${name} is not a block name.` };
        names[symbol] = name;
    }
    const grid = layers.split('/').map(layer => layer.split(',').map(row => row.replace(/\s/g, '')));
    const width = Math.max(...grid.flat().map(row => row.length));
    const depth = Math.max(...grid.map(layer => layer.length));
    if (grid.length > MAX_SIDE || width > MAX_SIDE || depth > MAX_SIDE)
        return { error: `A structure may be at most ${MAX_SIDE} blocks on each side; this one is ${width} x ${grid.length} x ${depth}.` };
    let cells = 0;
    const levels = [];
    for (const [level, rows] of grid.entries()) {
        const placement = [];
        for (const row of rows) {
            const line = [];
            for (const symbol of row.padEnd(width, ANY)) {
                if (!(symbol in names)) return { error: `"${symbol}" is not in the legend.` };
                if (names[symbol]) cells++;
                line.push(names[symbol]);
            }
            placement.push(line);
        }
        while (placement.length < depth) placement.push(Array(width).fill(''));
        levels.push({ level, coordinates: [Math.floor(x), Math.floor(y) + level, Math.floor(z)], placement });
    }
    if (cells === 0) return { error: 'The structure asks for no blocks.' };
    if (cells > MAX_CELLS) return { error: `A structure may ask for at most ${MAX_CELLS} cells; this one asks for ${cells}.` };
    return { blueprint: { levels }, cells };
}

/** The steps that build a blueprint: a pickaxe when stone is in the way, each material, then the region. */
export function structureSteps(blueprint, bot) {
    const need = item => b => materials(blueprint, b)[item] || 0;
    const steps = [haveStep('pickaxe', 'wooden_pickaxe', b => clearingTool(blueprint, b) ? 1 : 0, { satisfiedBy: PICKAXES })];
    for (const item of Object.keys(materials(blueprint, bot)).sort())
        steps.push(haveStep(item, item, need(item)));
    steps.push({
        id: 'structure', kind: 'build', label: 'clear and build the structure', subject: 'structure', needs: steps.map(step => step.id),
        done: b => remaining(blueprint, b).length === 0,
        run: b => buildRegion(b, blueprint),
        seconds: b => seconds(blueprint, b),
        estimate: b => estimate(blueprint, b),
    });
    return steps;
}

/** Build a structure written as a legend and layers at the given corner (see parseStructure). */
export async function buildStructure(agent, x, y, z, legend, layers) {
    const bot = agent.bot;
    const read = parseStructure(bot.registry, x, y, z, legend, layers);
    if (read.error) {
        skills.log(bot, read.error);
        return false;
    }
    const left = remaining(read.blueprint, bot).length;
    skills.log(bot, `Building a structure of ${read.cells} cells from ${Math.floor(x)}, ${Math.floor(y)}, ${Math.floor(z)}; ${left} differ now.`);
    return await runPlan(bot, structureSteps(read.blueprint, bot), { title: 'structure' });
}
