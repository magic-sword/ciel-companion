/**
 * The plan as a graph for people to see (CIEL's plan graph, plan v1): what the executor is
 * actually doing, read from the world, never a list made up beside it. A node is a step of the
 * plan (or, under it, a step obtainItem takes, or a choice); its kind is a game-independent verb,
 * its label the object in the game's words. The host sets bot.reportPlan to receive snapshots.
 *
 * node: { id, parent, kind, label, state, needs: [ids], estimate_s, choice: { question,
 *         options: [{ id, summary }], chosen } }
 * kind: obtain | make | build | find | wait | decide | do
 * state: pending | ready | running | done | failed | waiting_choice
 */
export const KINDS = ['obtain', 'make', 'build', 'find', 'wait', 'decide', 'do'];
export const STATES = ['pending', 'ready', 'running', 'done', 'failed', 'waiting_choice'];
const MAX_NODES = 64;
const SEND_MS = 1000;

let nextPlan = 1;

/** Start the view of a plan made of steps: { id, label (or subject, the object for people), kind, needs }. */
export function beginPlan(bot, steps, title) {
    bot.planView = {
        v: 1, plan_id: `plan-${Date.now().toString(36)}-${nextPlan++}`, revision: 0, title,
        nodes: steps.map(step => ({ id: step.id, parent: null, kind: step.kind ?? 'do', label: step.subject ?? step.label,
            state: 'pending', needs: [...(step.needs ?? [])], estimate_s: null })),
        current: [],
    };
    return bot.planView;
}

/** The view is kept while it is being added to: a plan inside a plan adds under the running step. */
export const activePlan = bot => bot.planView && !bot.planView.finished ? bot.planView : null;

/** Change a node, by id. */
export function setNode(bot, id, patch) {
    const node = bot.planView?.nodes.find(n => n.id === id);
    if (node) Object.assign(node, patch);
}

/** Put the steps under a node, replacing those it had (a plan is made again before every step). */
export function setChildren(bot, parent, children) {
    const view = bot.planView;
    if (!view) return;
    const kept = view.nodes.filter(n => !isUnder(view, n, parent));
    view.nodes = [...kept, ...children.map(child => ({ parent, needs: [], estimate_s: null, ...child }))].slice(0, MAX_NODES);
}

function isUnder(view, node, parent) {
    for (let p = node.parent; p; p = view.nodes.find(n => n.id === p)?.parent)
        if (p === parent) return true;
    return false;
}

/** Mark the plan finished (its last states stay to be seen) and send it at once. */
export function finishPlan(bot) {
    if (!bot.planView) return;
    bot.planView.finished = true;
    publish(bot, true);
}

/** Send the view to the host, at most once a second unless now is set. */
export function publish(bot, now = false) {
    const view = bot.planView;
    if (!view || !bot.reportPlan) return;
    view.current = view.nodes.filter(n => n.state === 'running' || n.state === 'waiting_choice').map(n => n.id);
    const send = () => {
        view.revision += 1;
        view.sentAt = Date.now();
        view.timer = null;
        const { timer, sentAt, finished, ...snapshot } = view;
        bot.reportPlan(structuredClone({ ...snapshot, finished: Boolean(finished) }));
    };
    if (now || !view.sentAt || Date.now() - view.sentAt >= SEND_MS) {
        clearTimeout(view.timer);
        send();
    } else if (!view.timer) {
        view.timer = setTimeout(send, SEND_MS - (Date.now() - view.sentAt));
        view.timer.unref?.();
    }
}
