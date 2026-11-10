"""Synthetic capability competition, installed only by the isolated benchmark entrypoint."""
import copy
import hashlib
import json
import os


FAMILIES = (
    ('smelt', '精錬設備で素材を精錬する', ('iron', 'gold', 'copper', 'glass', 'brick')),
    ('farm', '畑で作物を栽培・収穫する', ('wheat', 'carrot', 'potato', 'beetroot', 'melon')),
    ('breed', '動物に餌を与えて繁殖させる', ('cow', 'sheep', 'pig', 'chicken', 'rabbit')),
    ('escort', '指定した動物を囲いへ誘導する', ('cow', 'sheep', 'pig', 'chicken', 'rabbit')),
    ('store', '持ち物を指定収納へ預ける', ('chest', 'barrel', 'shulker', 'hopper', 'minecart')),
    ('inspect', '設備の状態を調べる', ('furnace', 'farm', 'portal', 'rail', 'beacon')),
    ('repair', '設備の壊れた部分を直す', ('bridge', 'road', 'fence', 'gate', 'rail')),
    ('build', '指定地点に設備を建てる', ('bridge', 'road', 'fence', 'gate', 'shelter')),
    ('mark', '地点を地図へ記録する', ('village', 'cave', 'mine', 'portal', 'base')),
    ('patrol', '指定した区域を巡回する', ('village', 'base', 'farm', 'coast', 'mine')),
    ('light', '区域に照明を設置する', ('village', 'base', 'farm', 'road', 'mine')),
    ('fish', '水域で釣りをする', ('river', 'lake', 'ocean', 'pond', 'canal')),
    ('trade', '村人と交易する', ('farmer', 'librarian', 'armorer', 'cleric', 'fletcher')),
    ('enchant', '道具にエンチャントを付ける', ('sword', 'axe', 'bow', 'helmet', 'boots')),
    ('dye', '指定色に染める', ('wool', 'bed', 'banner', 'glass', 'armor')),
    ('sort', '収納内の物を整理する', ('stone', 'wood', 'food', 'ore', 'tools')),
    ('harvest', '専用農場から資源を回収する', ('honey', 'bamboo', 'cactus', 'kelp', 'sugar_cane')),
    ('feed', '飼育中の動物に餌を与える', ('horse', 'wolf', 'cat', 'llama', 'camel')),
    ('survey', '区域の地形を調査する', ('desert', 'forest', 'mountain', 'swamp', 'ocean')),
    ('operate', '設置済み装置を操作する', ('lever', 'door', 'piston', 'dispenser', 'rail_switch')),
)


def configuration(environ=None):
    env = os.environ if environ is None else environ
    count = int(env.get('CIEL_BENCH_DISTRACTORS', '0'))
    surface = env.get('CIEL_BENCH_DISTRACTOR_SURFACE', 'both')
    if not 0 <= count <= 100 or surface not in ('work', 'catalog', 'both'):
        raise ValueError('Invalid benchmark distractor configuration')
    definitions = generate(count)
    return {'count': count, 'surface': surface, 'fixture_version': 1,
            'sha256': hashlib.sha256(json.dumps(definitions, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}


def generate(count):
    if type(count) is not int or not 0 <= count <= 100:
        raise ValueError('Distractor count must be 0..100')
    # Interleave families so even small counts include semantically close movement competitors.
    return [
        {'name': f'minecraft.{verb}_{targets[index]}',
         'description': f'{description}。対象: {targets[index]}。',
         'arguments': {'type': 'object', 'properties': {
             'x': {'type': 'number'}, 'z': {'type': 'number'}},
             'required': ['x', 'z'], 'additionalProperties': False},
         'constraints': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
        for index in range(5) for verb, description, targets in FAMILIES][:count]


def attach(env, config, record):
    """Use normal catalog/permission machinery; synthetic actions never reach Minecraft."""
    definitions = generate(config['count'])
    names = {d['name'] for d in definitions}
    tool_names = {n.replace('.', '_', 1) for n in names}
    if names & {d['name'] for d in env.profile['work']['capabilities']} or tool_names & set(env.meta):
        raise ValueError('Synthetic capability collides with real capability')
    if config['surface'] in ('work', 'both'):
        env.profile = copy.deepcopy(env.profile)
        env.profile['work']['capabilities'].extend(definitions)
    if config['surface'] in ('catalog', 'both'):
        for d in definitions:
            name = d['name'].replace('.', '_', 1)
            env.meta[name] = {'ciel/role': 'act'}
            env.tools.append(env._wrap(name, d['description'], d['arguments']))
    original = env._call

    async def call(name, args, **kwargs):
        if name in tool_names or args.get('capability') in names:
            record('benchmark_distractor_call', name=name, capability=args.get('capability'))
            return {'status': 'error', 'reason': 'benchmark_distractor', 'message': 'この操作は試験用で実行できません。'}
        return await original(name, args, **kwargs)

    if definitions:
        env._call = call
    record('benchmark_distractors', **config, work_count=len(env.profile['work']['capabilities']),
           catalog_count=len(env.tools))


def install():
    import game_env
    import debug_log
    if os.environ.get('CIEL_BENCHMARK') != '1' or os.environ.get('CIEL_AGENT_NAME') != 'ciel-task-bench':
        raise RuntimeError('Distractors require the dedicated benchmark agent')
    config = configuration()
    original = game_env.GameEnv.prepare

    async def prepare(env):
        ready = await original(env)
        if ready:
            if env.game != 'minecraft' or env.url != 'http://127.0.0.1:8773/mcp':
                raise RuntimeError('Distractors require the dedicated benchmark body')
            attach(env, config, debug_log.record)
        return ready

    game_env.GameEnv.prepare = prepare
