import * as mc from '../../utils/mcdata.js';
import * as world from './world.js';
import * as skills from './skills.js';
import { obtainItem, obtainSeconds, obtainEstimate } from './obtain.js';
import { within } from './deadline.js';
import { recordTime } from './timing.js';
import { SLACK } from './estimate.js';
import { beginPlan, activePlan, setNode, publish, finishPlan } from './planview.js';

/**
 * A plan is an ordered list of steps. Each step names the steps it needs, says whether the
 * state it is responsible for already holds (read from the world, never assumed), how to
 * bring that state about, and how long that may take. Steps are rerun from the world state,
 * so a step that something else already satisfied is skipped, and a step whose state is
 * lost again is redone. The plan's time is the sum of its steps' times: one slow step can
 * use only its own time, never the whole plan's.
 *
 * step: { id, label, kind, needs: [ids], done(bot) -> bool, run(bot) -> Promise, seconds(bot) -> number,
 *         estimate(bot) -> number }. The plan is shown as a graph (planview.js) while it runs.
 */
export async function runPlan(bot, steps, { tries = 2, title = '' } = {}) {
    const byId = new Map(steps.map(step => [step.id, step]));
    // The same plan carried on after a choice keeps its view; another plan starts its own.
    const key = steps.map(step => step.id).join('|');
    if (activePlan(bot)?.key !== key) beginPlan(bot, steps, title).key = key;
    const show = (running = null) => {
        for (const step of steps) {
            const state = step.done(bot) ? 'done' : step === running ? 'running'
                : (failures.get(step.id) || 0) >= tries ? 'failed'
                : step.needs.every(id => byId.get(id).done(bot)) ? 'ready' : 'pending';
            setNode(bot, step.id, { state, estimate_s: Math.round((step.estimate ?? step.seconds)(bot)) });
        }
        publish(bot);
    };
    // A step's estimate is its usual time; its seconds are its deadline, the most it may take.
    const remaining = () => steps.filter(step => !step.done(bot)).reduce((sum, step) => sum + (step.estimate ?? step.seconds)(bot), 0);
    const total = remaining();
    skills.log(bot, `Plan: ${steps.map(step => step.label).join(', ')}. About ${Math.round(total)}s.`);
    // The work that runs the plan may last as long as its steps take, with the slack each step
    // has (CIEL's work deadline). Told again after every step, as what is left can grow
    // (a sheep to look for); a work is never shortened by it.
    const report = () => bot.reportEstimate?.(remaining() * SLACK);
    report();
    const failures = new Map();
    for (;;) {
        if (bot.interrupt_code) {
            skills.log(bot, 'Stopped the plan.');
            show();
            finishPlan(bot);
            return false;
        }
        const pending = steps.filter(step => !step.done(bot));
        if (pending.length === 0) {
            skills.log(bot, 'Finished the plan.');
            show();
            finishPlan(bot);
            return true;
        }
        const step = pending.find(step => step.needs.every(id => byId.get(id).done(bot)));
        if (!step) {
            skills.log(bot, `Cannot continue: ${pending.map(step => step.label).join(', ')} still need earlier steps that are no longer done.`);
            show();
            finishPlan(bot);
            return false;
        }
        show(step);
        const seconds = step.seconds(bot);
        const began = Date.now();
        const asked = bot.pendingChoice;
        if (!await within(bot, () => step.run(bot), seconds))
            skills.log(bot, `Timed out on "${step.label}" after ${Math.round((Date.now() - began) / 1000)}s.`);
        recordTime('plan_step', began, { id: step.id, budget: Math.round(seconds), ok: step.done(bot) });
        report();
        if (bot.pendingChoice && bot.pendingChoice !== asked) {
            continueAfterChoice(bot, steps, { tries, title });
            const rest = steps.filter(other => !other.done(bot)).map(other => other.label);
            skills.log(bot, `The plan waits for that choice; choosing carries it on: ${rest.join(', ')}.`);
            show();
            setNode(bot, step.id, { state: 'waiting_choice' });
            publish(bot, true);
            return false;
        }
        if (step.done(bot)) continue;
        const count = (failures.get(step.id) || 0) + 1;
        failures.set(step.id, count);
        if (count >= tries) {
            const rest = steps.filter(other => !other.done(bot) && other !== step).map(other => other.label);
            skills.log(bot, `Could not ${step.label} after ${count} tries.` + (rest.length ? ` Not done yet: ${rest.join(', ')}.` : ''));
            show();
            finishPlan(bot);
            return false;
        }
    }
}

// A step stopped at a choice (such as how to get wool for a bed): each option first does what
// it chose, then the plan goes on from the world state. A further choice is wrapped the same way.
function continueAfterChoice(bot, steps, options) {
    const choice = bot.pendingChoice;
    choice.options = Object.fromEntries(Object.entries(choice.options).map(([id, go]) => [id, async () => {
        const asked = bot.pendingChoice;
        await go();
        if (bot.pendingChoice && bot.pendingChoice !== asked) {
            continueAfterChoice(bot, steps, options);
            return false;
        }
        return bot.interrupt_code ? false : await runPlan(bot, steps, options);
    }]));
}

const count = (bot, name) => world.getInventoryCounts(bot)[name] || 0;
// A step's amount may depend on the world, such as the seeds still needed for unsown cells,
// so a step stays done once what it gathered has been used up.
const amount = (num, bot) => typeof num === 'function' ? num(bot) : num;

// Seconds per executor step, the same basis as the long-horizon benchmark deadlines; the
// least a "have" step gets.
export const SECONDS_PER_ITEM_STEP = 40;

/** Have num of an item, made or mined by the crafting-plan executor, in the time its steps take. */
export function haveStep(id, item, num = 1, { needs = [], satisfiedBy = [item] } = {}) {
    return {
        id, needs, kind: 'obtain', label: `get ${typeof num === 'function' ? 'enough' : num} ${item}`,
        subject: typeof num === 'function' ? item : `${item} ×${num}`,
        done: bot => {
            const n = amount(num, bot);
            return n <= 0 || satisfiedBy.reduce((sum, name) => sum + count(bot, name), 0) >= n;
        },
        run: bot => obtainItem(bot, item, amount(num, bot)),
        seconds: bot => Math.max(SECONDS_PER_ITEM_STEP, obtainSeconds(bot, item, Math.max(1, amount(num, bot)))),
        estimate: bot => amount(num, bot) <= 0 ? 0 : obtainEstimate(bot, item, Math.max(1, amount(num, bot))),
    };
}

/** Have num of an item that only drops sometimes from breaking blocks, such as seeds from grass. */
export function dropStep(id, item, num, sources, { needs = [], perBlockSeconds = 2, batch = 8 } = {}) {
    const missing = bot => Math.max(0, amount(num, bot) - count(bot, item));
    return {
        id, needs, kind: 'obtain', label: `get ${typeof num === 'function' ? 'enough' : num} ${item} from ${sources.join(' or ')}`,
        subject: `${item} (${sources.join(' / ')})`,
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
        id, needs, kind: 'do', label: 'fill a bucket with water', subject: 'water_bucket',
        done: bot => !wanted(bot) || count(bot, 'water_bucket') > 0,
        run: bot => skills.useToolOn(bot, 'bucket', 'water'),
        seconds: () => 60,
    };
}
