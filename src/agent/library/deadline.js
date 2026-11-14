import * as skills from './skills.js';

/**
 * Run work for at most the given seconds. A pathfinding or pickup wait can hang without ever
 * failing, so a step past its time is stopped the same way an interrupt stops an action.
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
    skills.haltMovement(bot);
    // Let the stopped work settle before going on; never wait on it forever.
    await Promise.race([running, new Promise(resolve => setTimeout(resolve, 3000))]);
    return false;
}
