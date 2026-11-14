/**
 * Game knowledge for getting items from mobs, for Minecraft 1.21.11, taken from the Minecraft
 * Wiki page named in each entry. minecraft-data's entity loot leaves out drops that vary (a
 * sheep's wool follows its colour) and has no spawning rules, so they are written here; tests
 * check every name and the minecraft-data drops against this table.
 *
 * methods: how the mob gives items. Each lists the items and the [min, max] per mob, the tool
 *   it needs, and whether the mob stays (so it can give again).
 * spawn: where and when the mob appears, for the model to weigh and for searching.
 */
export const MOBS = {
    sheep: {
        hostile: false,
        spawn: { dimension: 'overworld', ground: 'grass_block', light: 'bright', time: 'any',
            note: 'Most appear when the land is first generated and few come back, so killing them empties the area.' },
        methods: {
            kill: { drops: { wool: [1, 1], mutton: [1, 2] } },
            shear: { tool: 'shears', stays: true, drops: { wool: [1, 3] },
                note: 'The wool grows back after the sheep eats grass.' },
        },
        breed: 'wheat',
        wiki: 'https://minecraft.wiki/w/Sheep',
    },
    cow: {
        hostile: false,
        spawn: { dimension: 'overworld', ground: 'grass_block', light: 'bright', time: 'any',
            note: 'Most appear when the land is first generated and few come back.' },
        methods: { kill: { drops: { leather: [0, 2], beef: [1, 3] } } },
        breed: 'wheat',
        wiki: 'https://minecraft.wiki/w/Cow',
    },
    chicken: {
        hostile: false,
        spawn: { dimension: 'overworld', ground: 'grass_block', light: 'bright', time: 'any',
            note: 'Most appear when the land is first generated and few come back.' },
        methods: { kill: { drops: { feather: [0, 2], chicken: [1, 1] } } },
        breed: 'wheat_seeds',
        wiki: 'https://minecraft.wiki/w/Chicken',
    },
    pig: {
        hostile: false,
        spawn: { dimension: 'overworld', ground: 'grass_block', light: 'bright', time: 'any',
            note: 'Most appear when the land is first generated and few come back.' },
        methods: { kill: { drops: { porkchop: [1, 3] } } },
        breed: 'carrot',
        wiki: 'https://minecraft.wiki/w/Pig',
    },
    spider: {
        hostile: true,
        spawn: { dimension: 'overworld', light: 'dark', time: 'night',
            note: 'Appears in the dark, on the surface at night; not at all on peaceful difficulty.' },
        methods: { kill: { drops: { string: [0, 2], spider_eye: [0, 1] } } },
        wiki: 'https://minecraft.wiki/w/Spider',
    },
    enderman: {
        hostile: true,
        spawn: { dimension: 'overworld or nether', light: 'dark', time: 'night',
            note: 'Rare on the overworld at night; common in the nether warped forest, which needs a nether portal. Not at all on peaceful difficulty.' },
        methods: { kill: { drops: { ender_pearl: [0, 1] },
            note: 'Fight it under a two-block-high roof it cannot enter, or trap it in a boat; looking at it makes it attack.' } },
        wiki: 'https://minecraft.wiki/w/Enderman',
    },
};

// Wool colours a sheep can carry, by the colour id in its metadata.
export const WOOL_COLORS = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray',
    'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black'];

/** The generic drop an item comes as ("wool" for every colour) and the colour, if any. */
export function dropKind(item) {
    const color = WOOL_COLORS.find(c => item === `${c}_wool`);
    return color ? { drop: 'wool', color } : { drop: item, color: null };
}

/**
 * The ways mobs give an item: [{ id: "kill:sheep", mob, method, tool, per: [min, max], color, stays }].
 */
export function mobWays(item) {
    const { drop, color } = dropKind(item);
    const ways = [];
    for (const [mob, entry] of Object.entries(MOBS)) {
        for (const [method, way] of Object.entries(entry.methods)) {
            if (!way.drops[drop]) continue;
            ways.push({ id: `${method}:${mob}`, mob, method, tool: way.tool ?? null, per: way.drops[drop],
                color, stays: Boolean(way.stays), hostile: entry.hostile });
        }
    }
    return ways;
}

/** How many mobs to expect to use for count items, from the average drop. */
export function mobsNeeded(way, count) {
    const average = (way.per[0] + way.per[1]) / 2;
    return average > 0 ? Math.ceil(count / average) : Infinity;
}
