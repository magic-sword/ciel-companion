import * as mc from '../../utils/mcdata.js';
import * as world from './world.js';
import * as skills from './skills.js';
import { within } from './deadline.js';
import { recordTime } from './timing.js';
import { getFromMob, countSuitable, EXPLORE_LEGS } from './hunt.js';
import { MOBS, mobWays, mobsNeeded } from './mobs.js';
import { baseStation } from './base.js';
import { expected, limit, SLACK, FLOOR } from './estimate.js';

/**
 * Obtain an item by executing its crafting plan step by step.
 * The plan (crafting, mining with the right tool, smelting, the crafting table) is rebuilt
 * from the actual inventory before every step, so consumed or extra items never leave it
 * stale, and each step is checked against the inventory afterwards. Only the order and
 * counts are decided here. Where an item has several ways (killing or shearing a sheep, or
 * crafting from string), the plan stops, lists them with their costs and waits for
 * !chooseOption; choices holds the ways already chosen.
 * @param {MinecraftBot} bot
 * @param {string} itemName the item to have.
 * @param {number} num how many to have in total. Defaults to 1.
 * @returns {Promise<boolean>} true once the inventory holds num items.
 * @example
 * await obtainItem(bot, "stone_pickaxe", 1);
 **/
export async function obtainItem(bot, itemName, num=1, { maxSteps=40, maxRepeats=2, choices={} }={}) {
    // A step that leaves its item count unchanged is a failure; the same step failing
    // maxRepeats times in a row stops the plan so the caller can choose what to do.
    let previous = null, repeats = 0, done = 0;
    for (let i = 0; i < maxSteps; i++) {
        if (bot.interrupt_code) {
            skills.log(bot, `Stopped obtaining ${itemName}.`);
            return false;
        }
        const inventory = world.getInventoryCounts(bot);
        if ((inventory[itemName] || 0) >= num) {
            skills.log(bot, `Obtained ${num} ${itemName} (${done} steps).`);
            return true;
        }
        const tableAvailable = stations(bot, inventory);
        const actions = mc.getCraftingActions(itemName, num, inventory, tableAvailable, choices);
        if (!actions || actions.length === 0) {
            skills.log(bot, `There is no known way to obtain ${itemName}.`);
            return false;
        }
        let step = actions[0];
        if (step.type === 'choose') {
            offerChoice(bot, itemName, num, step, choices, inventory, tableAvailable);
            return false;
        }
        // Mine everything the plan needs of that block in one trip, not one batch at a time.
        if (step.type === 'mine') {
            const count = actions.filter(a => a.type === 'mine' && a.item === step.item).reduce((n, a) => n + a.count, 0);
            step = { ...step, count };
        }
        const key = JSON.stringify(step);
        if (key !== previous) repeats = 0;
        previous = key;
        if (repeats >= maxRepeats) {
            skills.log(bot, `Could not ${describe(step)} after ${maxRepeats} tries; ${actions.length} steps remain for ${num} ${itemName}.`);
            return false;
        }
        const before = inventory[step.item] || 0;
        const began = Date.now();
        if (!await within(bot, () => perform(bot, step), stepSeconds(bot, step), describe(step)))
            skills.log(bot, `Timed out trying to ${describe(step)} after ${Math.round((Date.now() - began) / 1000)}s.`);
        done++;
        const gained = (world.getInventoryCounts(bot)[step.item] || 0) - before;
        recordTime(step.type, began, { item: step.item, count: step.count ?? step.produces ?? 1, gained,
            ...(step.method ? { method: step.method, mob: step.mob } : {}) });
        if (gained > 0) repeats = 0;
        else repeats++;
    }
    skills.log(bot, `Gave up obtaining ${itemName} after ${maxSteps} steps.`);
    return false;
}

// The plan's steps as obtainItem runs them: the mining of one block in one trip. A choice ends it.
function plannedSteps(bot, itemName, num) {
    const inventory = world.getInventoryCounts(bot);
    const actions = mc.getCraftingActions(itemName, num, inventory, stations(bot, inventory)) || [];
    const mined = new Map(), others = [];
    for (const step of actions) {
        if (step.type === 'choose') break;
        if (step.type === 'mine') mined.set(step.item, { ...step, count: (mined.get(step.item)?.count || 0) + step.count });
        else others.push(step);
    }
    return [...others, ...mined.values()];
}

/** The longest obtaining num items may take: the sum of its steps' deadlines. */
export function obtainSeconds(bot, itemName, num = 1) {
    return plannedSteps(bot, itemName, num).reduce((sum, step) => sum + stepSeconds(bot, step), 0);
}

/** The time obtaining num items usually takes (up to the 90th percentile of each step). */
export function obtainEstimate(bot, itemName, num = 1) {
    return plannedSteps(bot, itemName, num).reduce((sum, step) => sum + stepEstimate(bot, step), 0);
}

/**
 * The stations a plan can use without making one: carried, placed within 16 blocks, or at the
 * base within reach (craftRecipe and smeltItem walk there).
 */
export function stations(bot, inventory = world.getInventoryCounts(bot)) {
    const usable = name => (inventory[name] || 0) > 0 || world.getNearestBlock(bot, name, 16) !== null
        || baseStation(bot, name) !== null;
    return { crafting_table: usable('crafting_table'), furnace: usable('furnace') };
}

function describe(step) {
    if (step.type === 'craft') return `craft ${step.produces} ${step.item}`;
    if (step.type === 'smelt') return `smelt ${step.count} ${step.input}`;
    if (step.type === 'mob') return `${step.method} a ${step.mob} for ${step.item}`;
    return `mine ${step.count} ${step.item}` + (step.tool ? ` with a ${step.tool}` : '');
}

// The usual time of a step, from the measured step times (estimate.js). A mob not in sight is
// looked for first, leg by leg.
function stepEstimate(bot, step) {
    if (step.type === 'craft') return expected('craft');
    if (step.type === 'smelt') return expected('smelt') + expected('smelt_item', null, Math.max(0, step.count - 1));
    if (step.type === 'mob')
        return expected('mob', step.method) + (countSuitable(bot, step) === 0 ? EXPLORE_LEGS * expected('explore_leg') : 0);
    return expected('mine', step.item, step.count);
}

// A pathfinding or pickup wait can hang without ever failing, so every step gets its own
// deadline, its usual time with slack, and is stopped the same way an interrupt stops an action.
function stepSeconds(bot, step) {
    if (step.type === 'mine') return limit('mine', step.item, step.count);
    return Math.ceil(Math.max(FLOOR, stepEstimate(bot, step) * SLACK));
}

async function perform(bot, step) {
    if (step.type === 'craft')
        return await skills.craftRecipe(bot, step.item, step.times);
    if (step.type === 'smelt')
        return await skills.smeltItem(bot, step.input, step.count);
    if (step.type === 'mob')
        return await getFromMob(bot, step);
    return await skills.collectBlock(bot, step.source, step.count);
}

// List the ways to get the item the plan stopped at, each with what it costs, and wait for
// the model's !chooseOption. Choosing carries the same plan on with that way.
function offerChoice(bot, itemName, num, step, choices, inventory, tableAvailable) {
    const ways = mobWays(step.item);
    const lines = step.options.map(id => {
        const chosen = { ...choices, [step.item]: id };
        const plan = mc.getCraftingActions(itemName, num, inventory, tableAvailable, chosen) || [];
        const further = plan.some(a => a.type === 'choose') ? ', then another choice' : '';
        const unseen = unseenSources(bot, plan);
        const missing = unseen.length ? `, no ${unseen.join(' or ')} seen nearby to mine` : '';
        if (id === 'make') return `make: craft or mine ${step.item} instead (${plan.length} steps in all${missing}${further})`;
        const way = ways.find(w => w.id === id);
        const seen = countSuitable(bot, way);
        const facts = [`about ${mobsNeeded(way, step.count)} ${way.mob} needed`,
            seen ? `${seen} suitable ${way.mob} seen nearby` : `none seen nearby, so I look for them on ${MOBS[way.mob].spawn.ground ?? 'their ground'} first`];
        if (way.tool && !(inventory[way.tool] > 0)) facts.push(`a ${way.tool} to make first`);
        if (way.stays) facts.push(`the ${way.mob} stay`);
        if (way.hostile) facts.push('it fights back');
        if (unseen.length) facts.push(`no ${unseen.join(' or ')} seen nearby to mine`);
        facts.push(`${plan.length} steps in all${further}`);
        const notes = [MOBS[way.mob].methods[way.method].note, MOBS[way.mob].spawn.note].filter(Boolean).join(' ');
        return `${id}: ${facts.join(', ')}. ${notes}`.trim();
    });
    // Whether to choose or to ask the owner is the model's judgement; a choice made is told.
    const text = `To get ${num} ${itemName} I need ${step.count} ${step.item}, which can come several ways. Choose one with !chooseOption("id") using an id below and tell the owner in a few words which way you took, or ask the owner when it is theirs to decide.\n${lines.join('\n')}`;
    bot.pendingChoice = {
        question: `how to get ${step.count} ${step.item}`,
        text,
        options: Object.fromEntries(step.options.map(id =>
            [id, () => obtainItem(bot, itemName, num, { choices: { ...choices, [step.item]: id } })])),
    };
    skills.log(bot, text);
}

// Blocks a plan would mine that are not within 64 blocks, so a way that cannot be done here shows.
function unseenSources(bot, plan) {
    const sources = [...new Set(plan.filter(a => a.type === 'mine').map(a => a.source))];
    return sources.filter(source => !world.getNearestBlock(bot, skills.blockSources(source), 64));
}
