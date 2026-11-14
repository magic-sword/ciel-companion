/**
 * How long executor steps take, measured from the STEP_TIME lines of benchmark runs (median and
 * 90th percentile, in seconds; CIEL's results document names the runs). A step's deadline is its
 * 90th percentile with slack, so a slow step stops on its own time; a plan's estimate, which may
 * lengthen the work that runs it, is the sum of its steps' 90th percentiles.
 */
// Measured 2026-11-15 on the dedicated benchmark (seeds 11-13: the mc_* and long tasks, the farm,
// the bed and the house tasks; 1371 steps). Successful steps only where failures end at once.
export const TIMES = {
    craft: { median: 1.1, p90: 8.2 },              // per craft, with placing and taking back the table (n=546)
    smelt: { median: 12.4, p90: 21.5 },            // the first item, with fuel and the walk to the furnace
    smelt_item: { median: 12.4, p90: 12.4 },       // each further item (n=23 smelt steps)
    mine: {                                        // per block, with walking between blocks
        default: { median: 6.0, p90: 11.0 },
        dirt: { median: 1.6, p90: 2.4 },           // n=89
        cobblestone: { median: 1.8, p90: 2.8 },    // n=69
        coal: { median: 6.0, p90: 6.0 },           // the blocks gained (n=9)
        oak_log: { median: 5.5, p90: 10.0 },       // n=137
        raw_iron: { median: 9.0, p90: 24.3 },      // n=33
    },
    mob: { kill: { median: 9.7, p90: 11.4 }, shear: { median: 22.8, p90: 24.3 } },  // one sheep, found
    explore_leg: { median: 9.1, p90: 9.7 },        // n=10 legs reached
    tunnel_leg: { median: 20, p90: 30 },           // 16 blocks dug sideways (not measured yet)
    cell: { default: { median: 1.0, p90: 1.3 }, clear: { median: 0.9, p90: 1.2 } },  // placed or cleared (n=102)
};
// A step may run this much past its 90th percentile before it is stopped, and never less than FLOOR.
export const SLACK = 1.5;
export const FLOOR = 20;

const time = (kind, key) => {
    const entry = TIMES[kind];
    return entry?.[key] ?? entry?.default ?? entry;
};

/** The usual (p90) time of n of a kind of step, such as ('mine', 'oak_log', 8). */
export function expected(kind, key, n = 1) {
    return (time(kind, key)?.p90 ?? 0) * n;
}

/** The deadline of one step of n: its usual time with slack. */
export function limit(kind, key, n = 1) {
    return Math.ceil(Math.max(FLOOR, expected(kind, key, n) * SLACK));
}
