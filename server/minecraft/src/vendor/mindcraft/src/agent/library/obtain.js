import * as mc from '../../utils/mcdata.js';
import * as world from './world.js';
import * as skills from './skills.js';
import { within } from './deadline.js';

/**
 * Obtain an item by executing its crafting plan step by step.
 * The plan (crafting, mining with the right tool, smelting, the crafting table) is rebuilt
 * from the actual inventory before every step, so consumed or extra items never leave it
 * stale, and each step is checked against the inventory afterwards. Only the order and
 * counts are decided here; choosing between ways to get an item is left to the caller.
 * @param {MinecraftBot} bot
 * @param {string} itemName the item to have.
 * @param {number} num how many to have in total. Defaults to 1.
 * @returns {Promise<boolean>} true once the inventory holds num items.
 * @example
 * await obtainItem(bot, "stone_pickaxe", 1);
 **/
export async function obtainItem(bot, itemName, num=1, { maxSteps=40, maxRepeats=2 }={}) {
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
        const tableAvailable = (inventory['crafting_table'] || 0) > 0
            || world.getNearestBlock(bot, 'crafting_table', 16) !== null;
        const actions = mc.getCraftingActions(itemName, num, inventory, tableAvailable);
        if (!actions || actions.length === 0) {
            skills.log(bot, `There is no known way to obtain ${itemName}.`);
            return false;
        }
        let step = actions[0];
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
        if (!await within(bot, () => perform(bot, step), stepSeconds(step), describe(step)))
            skills.log(bot, `Timed out trying to ${describe(step)} after ${Math.round((Date.now() - began) / 1000)}s.`);
        done++;
        if ((world.getInventoryCounts(bot)[step.item] || 0) > before) repeats = 0;
        else repeats++;
    }
    skills.log(bot, `Gave up obtaining ${itemName} after ${maxSteps} steps.`);
    return false;
}

function describe(step) {
    if (step.type === 'craft') return `craft ${step.produces} ${step.item}`;
    if (step.type === 'smelt') return `smelt ${step.count} ${step.input}`;
    return `mine ${step.count} ${step.item}` + (step.tool ? ` with a ${step.tool}` : '');
}

// A pathfinding or pickup wait can hang without ever failing, so every step gets its own
// deadline and is stopped the same way an interrupt stops an action.
function stepSeconds(step) {
    if (step.type === 'craft') return 20;
    if (step.type === 'smelt') return 20 + 12 * step.count;
    return 20 + 15 * step.count;
}

async function perform(bot, step) {
    if (step.type === 'craft')
        return await skills.craftRecipe(bot, step.item, step.times);
    if (step.type === 'smelt')
        return await skills.smeltItem(bot, step.input, step.count);
    return await skills.collectBlock(bot, step.source, step.count);
}
