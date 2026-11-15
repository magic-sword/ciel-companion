#!/usr/bin/env python3
"""Look for a playable spawn: try seeds in a throwaway Minecraft server and report the spawn's biome
and the logs around it. Runs on the home server; the normal world and its server are not touched.

  python3 minecraft_seed_probe.py SEED [SEED ...]

For each seed it starts itzg/minecraft-server (the version of server/compose.yaml) on a temporary
data folder with no published port, waits for the world, and asks over RCON:
  - the world spawn (from level.dat) and its biome,
  - how many logs of each kind and how much water lie within 32 blocks of the spawn (/fill ... replace
    counts the blocks it replaces with air; the temporary world is thrown away),
  - the nearest village.
It prints one JSON line per seed and removes the temporary server.
"""
import gzip
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IMAGE = 'itzg/minecraft-server:2026.10.1-java21'
VERSION = '1.21.11'
LOGS = ['oak_log', 'birch_log', 'spruce_log', 'dark_oak_log', 'acacia_log', 'jungle_log', 'cherry_log', 'mangrove_log']
BIOMES = ['plains', 'sunflower_plains', 'meadow', 'forest', 'flower_forest', 'birch_forest', 'savanna', 'taiga',
          'ocean', 'river', 'beach', 'swamp', 'desert', 'snowy_plains', 'dark_forest', 'jungle', 'badlands',
          'windswept_hills', 'stony_shore', 'cherry_grove', 'old_growth_birch_forest', 'deep_ocean']


def nbt_spawn(path):
    """SpawnX/Y/Z ints, or the spawn compound's pos, from an uncompressed level.dat payload."""
    data = gzip.decompress(Path(path).read_bytes())
    found = {}
    for key in (b'SpawnX', b'SpawnY', b'SpawnZ'):
        i = data.find(b'\x03' + struct.pack('>H', len(key)) + key)
        if i >= 0:
            found[key.decode()[-1].lower()] = struct.unpack('>i', data[i + 3 + len(key):i + 7 + len(key)])[0]
    if len(found) == 3:
        return found['x'], found['y'], found['z']
    i = data.find(b'\x0b' + struct.pack('>H', 3) + b'pos')
    if i >= 0:
        n = struct.unpack('>i', data[i + 6:i + 10])[0]
        if n == 3:
            return struct.unpack('>iii', data[i + 10:i + 22])
    raise ValueError('spawn not found in level.dat')


def rcon(name, command):
    return subprocess.run(['docker', 'exec', name, 'rcon-cli', command], capture_output=True, text=True).stdout.strip()


def count(name, block, x, y, z, r, dy):
    total = 0
    for x0 in range(x - r, x + r, 32):
        for z0 in range(z - r, z + r, 32):
            out = rcon(name, f'fill {x0} {y - dy} {z0} {x0 + 31} {y + dy} {z0 + 31} minecraft:air replace minecraft:{block}')
            m = re.search(r'filled (\d+)', out)
            total += int(m[1]) if m else 0
    return total


def probe(seed):
    folder = Path(tempfile.mkdtemp(prefix='ciel-seed-'))
    name = 'ciel-seed-probe'
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
    try:
        subprocess.run(['docker', 'run', '-d', '--name', name, '-e', 'EULA=TRUE', '-e', 'TYPE=VANILLA', '-e', f'VERSION={VERSION}',
                        '-e', f'SEED={seed}', '-e', 'MEMORY=2G', '-e', 'ONLINE_MODE=FALSE', '-e', 'ENABLE_RCON=TRUE',
                        '-e', 'VIEW_DISTANCE=6', '-v', f'{folder}:/data', IMAGE], check=True, capture_output=True)
        until = time.monotonic() + 300
        while 'Done (' not in subprocess.run(['docker', 'logs', name], capture_output=True, text=True).stdout:
            if time.monotonic() > until:
                raise TimeoutError('server did not start')
            time.sleep(2)
        rcon(name, 'gamerule max_block_modifications 40000')
        rcon(name, 'save-all flush')
        time.sleep(2)
        x, y, z = nbt_spawn(folder / 'world/level.dat')
        # Spawn chunks are not kept loaded: load the area around the spawn before asking about it.
        rcon(name, f'forceload add {x - 32} {z - 32} {x + 31} {z + 31}')
        until = time.monotonic() + 60
        while not all(rcon(name, f'execute if loaded {a} {y} {b}').startswith('Test passed')
                      for a in (x - 32, x + 31) for b in (z - 32, z + 31)):
            if time.monotonic() > until:
                raise TimeoutError('spawn area did not load')
            time.sleep(1)
        biome = next((b for b in BIOMES if rcon(name, f'execute if biome {x} {y} {z} minecraft:{b}').startswith('Test passed')),
                     'other')
        logs = {b: count(name, b, x, y, z, 32, 12) for b in LOGS}
        water = count(name, 'water', x, y, z, 32, 6)
        village = rcon(name, f'execute positioned {x} {y} {z} run locate structure #minecraft:village')
        m = re.search(r'\((\d+) blocks away\)', village)
        return dict(seed=seed, spawn=[x, y, z], biome=biome, logs={k: v for k, v in logs.items() if v},
                    log_total=sum(logs.values()), water=water, village_blocks=int(m[1]) if m else None)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    for seed in sys.argv[1:]:
        try:
            print(json.dumps(probe(seed), ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({'seed': seed, 'error': f'{type(error).__name__}: {error}'}), flush=True)
