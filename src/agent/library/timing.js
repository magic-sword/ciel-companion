/**
 * How long each executor step took, one line per step in the body's log, for estimating the
 * time steps take (see the long-horizon design). Only the step's kind and size are written.
 */
export function recordTime(kind, began, fields = {}) {
    console.log(`STEP_TIME ${JSON.stringify({ kind, ...fields, seconds: Math.round((Date.now() - began) / 100) / 10 })}`);
}
