import * as mc from '../../utils/mcdata.js';
import * as world from './world.js';
import * as skills from './skills.js';
import { obtainItem } from './obtain.js';
import { within } from './deadline.js';

/**
 * A plan is an ordered list of steps. Each step names the steps it needs, says whether the
 * state it is responsible for already holds (read from the world, never assumed), how to
 * bring that state about, and how long that may take. Steps are rerun from the world state,
 * so a step that something else already satisfied is skipped, and a step whose state is
 * lost again is redone. The plan's time is the sum of its steps' times: one slow step can
 * use only its own time, never the whole plan's.
 *
 * step: { id, label, needs: [ids], done(bot) -> bool, run(bot) -> Promise, seconds(bot) -> number }
 */
export async function runPlan(bot, steps, { tries = 2 } = {}) {
    const byId = new Map(steps.map(step => [step.id, step]));
    const total = steps.filter(step => !step.done(bot)).reduce((sum, step) => sum + step.seconds(bot), 0);
    skills.log(bot, `Plan: ${steps.map(step => step.label).join(', ')}. About ${Math.round(total)}s.`);
    const failures = new Map();
    for (;;) {
        if (bot.interrupt_code) {
            skills.log(bot, 'Stopped the plan.');
            return false;
        }
        const pending = steps.filter(step => !step.done(bot));
        if (pending.length === 0) {
            skills.log(bot, 'Finished the plan.');
            return true;
        }
        const step = pending.find(step => step.needs.every(id => byId.get(id).done(bot)));
        if (!step) {
            skills.log(bot, `Cannot continue: ${pending.map(step => step.label).join(', ')} still need earlier steps that are no longer done.`);
            return false;
        }
        const seconds = step.seconds(bot);
        const began = Date.now();
        if (!await within(bot, () => step.run(bot), seconds))
            skills.log(bot, `Timed out on "${step.label}" after ${Math.round((Date.now() - began) / 1000)}s.`);
        if (step.done(bot)) continue;
        const count = (failures.get(step.id) || 0) + 1;
        failures.set(step.id, count);
        if (count >= tries) {
            const rest = steps.filter(other => !other.done(bot) && other !== step).map(other => other.label);
            skills.log(bot, `Could not ${step.label} after ${count} tries.` + (rest.length ? ` Not done yet: ${rest.join(', ')}.` : ''));
            return false;
        }
    }
}

const count = (bot, name) => world.getInventoryCounts(bot)[name] || 0;
// A step's amount may depend on the world, such as the seeds still needed for unsown cells,
// so a step stays done once what it gathered has been used up.
const amount = (num, bot) => typeof num === 'function' ? num(bot) : num;

// Seconds per executor step, the same basis as the long-horizon benchmark deadlines.
export const SECONDS_PER_ITEM_STEP = 40;

/** Have num of an item, made or mined by the crafting-plan executor. */
export function haveStep(id, item, num = 1, { needs = [], satisfiedBy = [item] } = {}) {
    return {
        id, needs, label: `get ${typeof num === 'function' ? 'enough' : num} ${item}`,
        done: bot => {
            const n = amount(num, bot);
            return n <= 0 || satisfiedBy.reduce((sum, name) => sum + count(bot, name), 0) >= n;
        },
        run: bot => obtainItem(bot, item, amount(num, bot)),
        seconds: bot => {
            const inventory = world.getInventoryCounts(bot);
            const table = (inventory.crafting_table || 0) > 0 || world.getNearestBlock(bot, 'crafting_table', 16) !== null;
            const actions = mc.getCraftingActions(item, Math.max(1, amount(num, bot)), inventory, table) || [];
            return SECONDS_PER_ITEM_STEP * Math.max(1, actions.length);
        },
    };
}

/** Have num of an item that only drops sometimes from breaking blocks, such as seeds from grass. */
export function dropStep(id, item, num, sources, { needs = [], perBlockSeconds = 2, batch = 8 } = {}) {
    const missing = bot => Math.max(0, amount(num, bot) - count(bot, item));
    return {
        id, needs, label: `get ${typeof num === 'function' ? 'enough' : num} ${item} from ${sources.join(' or ')}`,
        done: bot => missing(bot) === 0,
        run: async bot => {
            let barren = 0;
            while (missing(bot) > 0 && !bot.interrupt_code && barren < 3) {
                const before = count(bot, item);
                const block = world.getNearestBlock(bot, sources, 64);
                if (!block) {
                    skills.log(bot, `No ${sources.join(' or ')} nearby to get ${item} from.`);
                    return;
                }
                await skills.collectBlock(bot, block.name, batch);
                barren = count(bot, item) > before ? 0 : barren + 1;
            }
        },
        // Seeds drop from about one grass in eight, so each missing one costs a batch.
        seconds: bot => 20 + perBlockSeconds * batch * missing(bot),
    };
}

/** Fill an empty bucket at the nearest water source while water is still wanted. */
export function fillBucketStep(id, wanted, { needs = [] } = {}) {
    return {
        id, needs, label: 'fill a bucket with water',
        done: bot => !wanted(bot) || count(bot, 'water_bucket') > 0,
        run: bot => skills.useToolOn(bot, 'bucket', 'water'),
        seconds: () => 60,
    };
}
