import * as skills from './skills.js';

// How long stopped work may take to notice the stop and end.
const SETTLE_SECONDS = 10;

/**
 * Run work for at most the given seconds. A pathfinding or pickup wait can hang without ever
 * failing, so a step past its time is stopped the same way an interrupt stops an action: the
 * interrupt flag is raised until the work ends, then lowered again unless a real interrupt came
 * meanwhile (requestInterrupt clears bot.deadlineStop). Stopping only the movement would leave
 * the work running beside whatever comes next; a retry of the same step then digs against it,
 * and each dig cancels the other.
 * @returns {Promise<boolean>} false when the time ran out.
 */
export async function within(bot, work, seconds, describe = 'do that') {
    let timer;
    const running = Promise.resolve().then(work).then(() => true, err => {
        skills.log(bot, `Failed to ${describe}: ${err?.message ?? err}.`);
        return true;
    });
    const expired = new Promise(resolve => { timer = setTimeout(() => resolve(false), seconds * 1000); });
    const finished = await Promise.race([running, expired]);
    clearTimeout(timer);
    if (finished) return true;
    const token = {};
    const ours = !bot.interrupt_code;
    if (ours) {
        bot.interrupt_code = true;
        bot.deadlineStop = token;
    }
    skills.haltMovement(bot);
    let wait;
    const ended = await Promise.race([running.then(() => true),
        new Promise(resolve => { wait = setTimeout(() => resolve(false), SETTLE_SECONDS * 1000); })]);
    clearTimeout(wait);
    if (!ended) skills.log(bot, `Could not stop "${describe}" within ${SETTLE_SECONDS}s; going on.`);
    if (ours && bot.deadlineStop === token) {
        bot.deadlineStop = null;
        bot.interrupt_code = false;
    }
    return false;
}
