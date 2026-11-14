/**
 * How long executor steps take, measured from the STEP_TIME lines of benchmark runs (median and
 * 90th percentile, in seconds; CIEL's results document names the runs). A step's deadline is its
 * 90th percentile with slack, so a slow step stops on its own time; a plan's estimate, which may
 * lengthen the work that runs it, is the sum of its steps' 90th percentiles.
 */
export const TIMES = {
    craft: { median: 1.0, p90: 8.6 },              // per craft, with placing and taking back the table
    smelt: { median: 13.8, p90: 33.9 },            // per smelt step of a few items
    smelt_item: { median: 10, p90: 12 },           // each further item in the furnace
    mine: {                                        // per block, with walking between blocks
        default: { median: 6.0, p90: 11.0 },
        oak_log: { median: 7.1, p90: 10.8 },
        cobblestone: { median: 1.8, p90: 4.6 },
        coal: { median: 5.6, p90: 6.1 },
        raw_iron: { median: 9.5, p90: 29.0 },
    },
    mob: { kill: { median: 15, p90: 40 }, shear: { median: 20, p90: 75 } },
    explore_leg: { median: 15, p90: 30 },
    cell: { default: { median: 3, p90: 15 } },
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
