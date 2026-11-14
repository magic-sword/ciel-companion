"""Farm tasks: the goal is a state of blocks, not an inventory count.

The arena surface is stone with exactly one grass patch the size of the farm, so the place is
fixed and the result can be read cell by cell. A pond gives water for the bucket and a field of
short grass on moss (moss is not farmland ground) gives the seeds. The layout seed moves the
patch, pond and field; the trees stay on the other side.
"""

CROPS = {'wheat'}


def validate(task):
    farm = task['farm']
    if set(farm) != {'size', 'crop'} or farm['crop'] not in CROPS or farm['size'] not in (3, 5):
        raise ValueError('farm must be {"size": 3 or 5, "crop": "wheat"}')
    if task['forest'] != 'near' or task.get('surface') != 'stone' or 'item' in task:
        raise ValueError('Farm tasks use a near forest on a stone surface and no target item')


def layout(rng, side, size):
    """Places on the side away from the trees (side is the trees' x direction)."""
    away = -side
    offset = rng.randint(0, 3)
    xs = sorted(away*(8 + offset + i) for i in range(size))
    z0 = rng.randint(-3, 3 - size + 1)
    patch = (xs[0], z0, xs[-1], z0 + size - 1)
    middle = (xs[size//2], z0 + size//2)
    pond_x = sorted(away*(19 + offset + i) for i in range(2))
    pond_z = rng.randint(-3, 2)
    pond = (pond_x[0], pond_z, pond_x[1], pond_z + 1)
    field_x = sorted((away*26, away*37))
    field = (field_x[0], -6, field_x[1], 5)
    goal = [[x, 64, z, 'wheat'] for x in range(patch[0], patch[2] + 1) for z in range(patch[1], patch[3] + 1)
            if (x, z) != middle]
    goal.append([middle[0], 63, middle[1], 'water'])
    return {'patch': patch, 'pond': pond, 'field': field, 'goal_blocks': goal}


def commands(farm):
    """Fixture commands, after the stone surface is laid."""
    x1, z1, x2, z2 = farm['patch']
    px1, pz1, px2, pz2 = farm['pond']
    fx1, fz1, fx2, fz2 = farm['field']
    return [f'fill {x1} 63 {z1} {x2} 63 {z2} minecraft:grass_block',
            f'fill {px1} 63 {pz1} {px2} 63 {pz2} minecraft:water',
            f'fill {fx1} 63 {fz1} {fx2} 63 {fz2} minecraft:moss_block',
            f'fill {fx1} 64 {fz1} {fx2} 64 {fz2} minecraft:short_grass']


def checks(farm):
    """Blocks that must be in place after the fixture, as (x, y, z, block)."""
    x1, z1, _, _ = farm['patch']
    px1, pz1, _, _ = farm['pond']
    fx1, fz1, _, _ = farm['field']
    return [(x1, 63, z1, 'grass_block'), (px1, 63, pz1, 'water'), (fx1, 64, fz1, 'short_grass')]


def progress(goal_blocks):
    return round(sum(goal_blocks)/len(goal_blocks), 3) if goal_blocks else None
