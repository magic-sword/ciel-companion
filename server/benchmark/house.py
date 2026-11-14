"""House tasks: build an upstream Mindcraft NPC house plan (src/agent/npc/construction/*.json).

The arena surface is stone with one grass patch exactly the size of the house, so the place is
fixed (the body builds on grass or dirt) and the result is read cell by cell for each way the
house can be turned to fit the patch. A dirt pile smaller than the house gives dirt without
being a place to build. The plans need a bed: with a pasture, the sheep are out of sight at the
end of a lane four blocks wide beyond the arena wall (too narrow to build on), so the body has
to look for them.
"""
import json
from pathlib import Path

PLANS = Path(__file__).resolve().parents[1]/'minecraft/src/vendor/mindcraft/src/agent/npc/construction'
# What the plan's generic names accept, as RCON block predicates (any one of them).
ACCEPT = {'dirt': ['#minecraft:dirt'], 'planks': ['#minecraft:planks'], 'log': ['#minecraft:logs'],
          'door': ['#minecraft:wooden_doors'], 'bed': ['#minecraft:beds'],
          'torch': ['minecraft:torch', 'minecraft:wall_torch']}
PLAN_NAMES = ('dirt_shelter',)
LANE_Z = (-2, 1)
LANE_X = (48, 103)
PASTURE = (104, -6, 115, 5)
FAR_END = 140


def load(name):
    if name not in PLAN_NAMES:
        raise ValueError(f'house plan must be one of {PLAN_NAMES}')
    return json.loads((PLANS/f'{name}.json').read_text(encoding='utf-8'))


def rotate(rows, turns):
    """The same quarter turns as house.js."""
    for _ in range(turns % 4):
        rows = [list(reversed([row[x] for row in rows])) for x in range(len(rows[0]))]
    return rows


def footprint(plan, turns=0):
    level = rotate(plan['blocks'][0], turns)
    return len(level[0]), len(level)


def validate(task):
    house = task['house']
    if set(house) - {'plan', 'pasture'} or 'plan' not in house or house.get('pasture', False) not in (True, False):
        raise ValueError('house must be {"plan": name, "pasture": bool}')
    load(house['plan'])
    if task['forest'] != 'near' or task.get('surface') != 'stone' or 'item' in task:
        raise ValueError('House tasks use a near forest on a stone surface and no target item')
    if house.get('pasture') and set(task.get('mobs', {})) != {'sheep'}:
        raise ValueError('A pasture holds the sheep')


def cells(plan, corner, turns):
    """(x, y, z, predicates) for every cell the plan fixes, the house turned turns times."""
    x0, ground, z0 = corner
    out = []
    for i, rows in enumerate(plan['blocks']):
        y = ground + 1 + plan['offset'] + i
        for dz, row in enumerate(rotate(rows, turns)):
            for dx, name in enumerate(row):
                if name:
                    out.append([x0 + dx, y, z0 + dz, ACCEPT.get(name, [f'minecraft:{name}'])])
    return out


def layout(rng, side, name):
    """The patch on the side away from the trees (side is the trees' x direction), the dirt pile
    beyond the trees' rows, and the goal cells for each turn of the house that fits the patch."""
    plan = load(name)
    width, depth = footprint(plan)
    away = -side
    offset = rng.randint(0, 3)
    xs = sorted(away*(8 + offset + i) for i in range(width))
    z0 = rng.randint(-4, 4 - depth + 1)
    patch = (xs[0], z0, xs[-1], z0 + depth - 1)
    pile_x = sorted(side*(3 + i) for i in range(5))
    pile = (pile_x[0], -23, pile_x[-1], -19)
    corner = (patch[0], 63, patch[1])
    goals = [cells(plan, corner, turns) for turns in range(4) if footprint(plan, turns) == (width, depth)]
    return {'plan': name, 'patch': patch, 'pile': pile, 'goal_layouts': goals}


def commands(house, pasture):
    """Fixture commands, after the stone surface is laid."""
    x1, z1, x2, z2 = house['patch']
    px1, pz1, px2, pz2 = house['pile']
    out = [f'fill {x1} 63 {z1} {x2} 63 {z2} minecraft:grass_block',
           f'fill {px1} 64 {pz1} {px2} 66 {pz2} minecraft:dirt']
    if pasture:
        # Reset the land beyond the arena wall (other fixtures change it), then the lane and pasture.
        out.append(f'forceload add {LANE_X[0]} -17 {FAR_END} 17')
        out.append(f'kill @e[type=!minecraft:player,x={LANE_X[0]},y=59,z=-17,dx={FAR_END - LANE_X[0]},dy=40,dz=34]')
        for y in range(60, 82):
            block = 'bedrock' if y == 60 else 'stone' if y <= 63 else 'air'
            out.append(f'fill {LANE_X[0] + 1} {y} -17 {FAR_END} {y} 17 minecraft:{block}')
        for wall in [(LANE_X[0] + 1, -17, FAR_END, -17), (LANE_X[0] + 1, 17, FAR_END, 17), (FAR_END, -17, FAR_END, 17)]:
            out.append(f'fill {wall[0]} 61 {wall[1]} {wall[2]} 81 {wall[3]} minecraft:bedrock')
        out.append(f'fill {LANE_X[0]} 64 {LANE_Z[0]} {LANE_X[0]} 81 {LANE_Z[1]} minecraft:air')
        out.append(f'fill {LANE_X[0]} 63 {LANE_Z[0]} {LANE_X[1]} 63 {LANE_Z[1]} minecraft:grass_block')
        out.append(f'fill {PASTURE[0]} 63 {PASTURE[1]} {PASTURE[2]} 63 {PASTURE[3]} minecraft:grass_block')
    return out


def checks(house, pasture):
    """Blocks that must be in place after the fixture, as (x, y, z, block)."""
    x1, z1, _, _ = house['patch']
    px1, pz1, _, _ = house['pile']
    out = [(x1, 63, z1, 'grass_block'), (px1, 66, pz1, 'dirt')]
    if pasture:
        out += [(LANE_X[0], 63, LANE_Z[0], 'grass_block'), (LANE_X[0], 64, LANE_Z[0], 'air'), (PASTURE[0], 63, PASTURE[1], 'grass_block')]
    return out


def mob_spot(rng):
    """Where a pasture animal is summoned."""
    return rng.randint(PASTURE[0] + 1, PASTURE[2] - 1), rng.randint(PASTURE[1] + 1, PASTURE[3] - 1)
