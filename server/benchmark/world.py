"""Privileged RCON oracle. Never exposed as an agent tool.

All fixture mutations require the benchmark marker and an exclusive world lease.
The arena is rebuilt per trial; seeds choose layouts, not Minecraft world seeds.
"""
import math
import random
import re
import socket
import struct
import time
import uuid

from .farm import layout as farm_layout, commands as farm_commands, checks as farm_checks

MARKER = 'ciel-benchmark-v1'
OBJECTIVE = 'cielbench'
ITEM = re.compile(r'^[a-z][a-z0-9_]*$')


class Rcon:
    def __init__(self, password, host='127.0.0.1', port=25576, timeout=10):
        if host not in ('127.0.0.1', 'localhost', '::1') or port == 25575:
            raise ValueError('Use the dedicated benchmark RCON on loopback, not production port 25575')
        self.address, self.timeout, self.password = (host,port), timeout, password
        self.sock = None
        self.serial = 0
        self._connect()

    def _connect(self):
        self.close()
        self.sock = socket.create_connection(self.address, self.timeout)
        try:
            self._send(1, 3, self.password)
            while True:
                rid, kind, _ = self._read()
                if rid == -1:
                    raise RuntimeError('Benchmark RCON authentication failed')
                if rid == 1 and kind == 2:
                    break
            self.last_used = time.monotonic()
        except BaseException:
            self.close()
            raise

    def _send(self, rid, kind, text):
        packet = struct.pack('<ii', rid, kind) + text.encode('utf-8') + b'\0\0'
        self.sock.sendall(struct.pack('<i', len(packet)) + packet)

    def _exact(self, count):
        data = b''
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError('Benchmark RCON disconnected')
            data += chunk
        return data

    def _read(self):
        size = struct.unpack('<i', self._exact(4))[0]
        if not 10 <= size <= 4_194_304:
            raise ValueError('Invalid RCON packet length')
        packet = self._exact(size)
        rid, kind = struct.unpack('<ii', packet[:8])
        return rid, kind, packet[8:-2].decode('utf-8')

    def command(self, text):
        # Inference / shutdown can leave RCON idle long enough for the server to close it.
        # Reconnect BEFORE sending; never retry a possibly applied give/fill command.
        if time.monotonic()-self.last_used >= 5:
            self._connect()
        self.serial += 2
        rid, sentinel = self.serial + 10, self.serial + 11
        self._send(rid, 2, text)
        # Minecraft expects one request frame at a time. Wait for the first response
        # before sending the delimiter, so TCP cannot combine two request frames.
        response_id, _, data = self._read()
        if response_id != rid:
            raise ValueError('Unexpected RCON response id')
        parts = [data]
        # A second request delimits multi-packet responses without relying on timing.
        self._send(sentinel, 2, '')
        while True:
            response_id, _, data = self._read()
            if response_id == sentinel:
                self.last_used = time.monotonic()
                return ''.join(parts)
            if response_id != rid:
                raise ValueError('Unexpected RCON response id')
            parts.append(data)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None


class World:
    def __init__(self, rcon, player='Ciel_Debug'):
        if not re.fullmatch(r'[A-Za-z0-9_]{1,16}', player):
            raise ValueError('Invalid benchmark player name')
        self.rcon, self.player = rcon, player
        self.lease = None

    def guard(self):
        answer = self.rcon.command('data get storage ciel_benchmark:meta suite')
        if not answer.rstrip().endswith('"' + MARKER + '"'):
            raise RuntimeError('Not a marked benchmark world; refusing to modify it')

    def scalar(self, command, *, success=False):
        self.rcon.command(f'scoreboard players set #probe {OBJECTIVE} 0')
        self.rcon.command(f'execute store {"success" if success else "result"} score #probe {OBJECTIVE} run {command}')
        text = self.rcon.command(f'scoreboard players get #probe {OBJECTIVE}')
        match = re.search(r'(-?\d+)\s+\[' + OBJECTIVE + r'\]\s*$', text)
        if match is None:
            raise RuntimeError('Cannot parse authoritative scoreboard result')
        return int(match[1])

    def acquire(self):
        self.guard()
        self.rcon.command(f'scoreboard objectives add {OBJECTIVE} dummy')
        self.rcon.command('scoreboard objectives add cieldeaths deathCount')
        token = uuid.uuid4().hex
        # The condition and write execute atomically on the Minecraft server thread.
        self.rcon.command('execute unless data storage ciel_benchmark:meta active run '
                          f'data modify storage ciel_benchmark:meta active set value "{token}"')
        answer = self.rcon.command('data get storage ciel_benchmark:meta active')
        if not answer.rstrip().endswith('"' + token + '"'):
            raise RuntimeError('Benchmark world is already leased (or stale lease remains)')
        self.lease = token

    def release(self):
        if self.lease:
            self.rcon.command('execute if data storage ciel_benchmark:meta '
                              f'{{active:"{self.lease}"}} run data remove storage ciel_benchmark:meta active')
            self.lease = None

    def _write(self, command):
        answer = self.rcon.command(command)
        if any(s in answer for s in ('Unknown or incomplete command', 'Incorrect argument', 'No player was found',
                                      'Cannot access', 'outside of the world', 'not loaded', 'too many blocks')):
            raise RuntimeError('Fixture command failed: ' + command.split()[0])

    def reset(self, task, seed):
        self.guard()
        if not self.lease:
            raise RuntimeError('Fixture reset requires the world lease')
        self.navigation = task.get('navigation')
        self.spatial = task.get('spatial')
        self.farm = None
        if self.navigation:
            if not self.scalar('execute if entity Bench_Owner', success=True):
                raise RuntimeError('Benchmark fixture owner is not online')
            self._write('gamemode creative Bench_Owner')
            self._write('tp Bench_Owner 0.5 85 0.5')
        elif self.scalar('execute if entity Bench_Owner', success=True):
            self._write('tp Bench_Owner 0.5 128 400.5')
        if not self.scalar(f'execute if entity {self.player}', success=True):
            raise RuntimeError('Benchmark bot is not online')
        # Teleport above the arena before replacing it. Each fill stays under 32768 blocks.
        for command in [f'gamemode creative {self.player}', f'tp {self.player} 0.5 85 0.5',
                        'forceload add -48 -48 48 48',
                        'kill @e[type=!minecraft:player,x=-48,y=59,z=-48,dx=96,dy=40,dz=96]',
                        f'clear {self.player}', f'effect clear {self.player}']:
            self._write(command)
        self._write(f'scoreboard players set {self.player} cieldeaths 0')
        for y in range(60, 82):
            block = 'bedrock' if y == 60 else 'stone' if y < 63 else task.get('surface','grass_block') if y == 63 else 'air'
            self._write(f'fill -48 {y} -48 48 {y} 48 minecraft:{block}')
        # Contain exploration, so changes outside the arena cannot affect later trials.
        for x1, z1, x2, z2 in [(-48,-48,48,-48),(-48,48,48,48),(-48,-48,-48,48),(48,-48,48,48)]:
            self._write(f'fill {x1} 60 {z1} {x2} 81 {z2} minecraft:bedrock')
        if self.navigation and self.navigation.get('locator_only'):
            end = 416 if self.navigation['targets'][0][0] > 270 else 288
            self._write(f'forceload add 32 -16 {end} 16')
            for y in range(60, 82):
                block = 'bedrock' if y == 60 else 'stone' if y < 63 else 'grass_block' if y == 63 else 'air'
                self._write(f'fill 32 {y} -16 {end} {y} 16 minecraft:{block}')
            for z in (-16, 16):
                self._write(f'fill 32 60 {z} {end} 81 {z} minecraft:bedrock')
            self._write(f'fill {end} 60 -16 {end} 81 16 minecraft:bedrock')
        rng = random.Random(seed)
        if task['forest'] == 'none':
            trees = []
        elif task['forest'] == 'far':
            trees = [(38 + seed % 5, z) for z in (-8, 0, 8)]
        elif task['forest'] == 'many':
            trees = [(x + seed % 5, z) for x in (6,12,18,24) for z in (-12,-6,0,6)]
        elif task['forest'] == 'near':
            side = rng.choice((-1, 1))
            trees = [(side*(x + seed % 5), rng.choice((-6, 0, 6))) for x in (6,12,18)]
        else:
            raise ValueError('Unknown fixture forest')
        for x, z in trees:
            self._write(f'fill {x} 64 {z} {x} 67 {z} minecraft:oak_log[axis=y]')
        # Ore blocks set into the ground surface, away from the trees and the spawn point.
        ores = []
        for name, count in sorted(task.get('ores', {}).items()):
            for _ in range(count):
                while True:
                    x, z = rng.randint(-14, 14), rng.choice((-1, 1))*rng.randint(10, 16)
                    if (x, z) not in {(ox, oz) for _, ox, oz in ores}:
                        break
                ores.append((name, x, z))
                self._write(f'setblock {x} 63 {z} minecraft:{name}')
        if task.get('farm'):
            self.farm = farm_layout(rng, side, task['farm']['size'])
            for command in farm_commands(self.farm):
                self._write(command)
        for item, count in task['inventory'].items():
            if not ITEM.fullmatch(item) or not 1 <= count <= 64:
                raise ValueError('Invalid fixture inventory')
            self._write(f'give {self.player} minecraft:{item} {count}')
        if self.spatial:
            for x,y,z,name in self.spatial['initial'] + self.spatial['preserve']:
                self._write(f'setblock {x} {y} {z} minecraft:{name}')
        for command in ['time set noon', 'weather clear', 'difficulty peaceful',
                        f'effect give {self.player} minecraft:saturation 1 10 true',
                        f'effect give {self.player} minecraft:instant_health 1 10 true',
                        f'spawnpoint {self.player} 0 64 0', f'tp {self.player} 0.5 64 0.5 0 0',
                        f'gamemode survival {self.player}']:
            self._write(command)
        for x, z in trees:
            if not self.scalar(f'execute if block {x} 64 {z} minecraft:oak_log', success=True):
                raise RuntimeError('Fixture resource placement failed')
        for name, x, z in ores:
            if not self.scalar(f'execute if block {x} 63 {z} minecraft:{name}', success=True):
                raise RuntimeError('Fixture ore placement failed')
        for x, y, z, name in farm_checks(self.farm) if self.farm else []:
            if not self.scalar(f'execute if block {x} {y} {z} minecraft:{name}', success=True):
                raise RuntimeError('Fixture farm placement failed')
        if self.navigation:
            self.move_target(self.navigation['targets'][0])
        return {'layout_seed': seed, 'trees': trees, 'arena': [-48,60,-48,48,81,48],
                **({'ores': [[name, x, 63, z] for name, x, z in ores]} if ores else {}),
                **({'farm': self.farm} if self.farm else {})}

    def move_target(self, position):
        self.guard()
        if not self.lease:
            raise RuntimeError('Moving the fixture owner requires the world lease')
        x,y,z = position
        if not (-40 <= x <= 400 and y == 64 and -40 <= z <= 40):
            raise ValueError('Target outside the navigation fixture')
        self._write(f'tp Bench_Owner {x} {y} {z}')

    def snapshot(self, items):
        if not self.scalar(f'execute if entity {self.player}', success=True):
            raise RuntimeError('Benchmark bot disconnected')
        inventory = {}
        for item in sorted(set(items)):
            if not ITEM.fullmatch(item):
                raise ValueError('Invalid item id')
            inventory[item] = self.scalar(f'clear {self.player} minecraft:{item} 0')
        position = [self.scalar(f'data get entity {self.player} Pos[{i}] 1000') / 1000 for i in range(3)]
        health = self.scalar(f'data get entity {self.player} Health 1000') / 1000
        deaths = self.scalar(f'scoreboard players get {self.player} cieldeaths')
        result = {'inventory': inventory, 'position': position, 'health': health, 'deaths': deaths}
        if getattr(self, 'spatial', None):
            for key, group in [('spatial_expected','expected'),('spatial_preserved','preserve')]:
                result[key] = [bool(self.scalar(f'execute if block {x} {y} {z} minecraft:{name}', success=True))
                               for x,y,z,name in self.spatial[group]]
        if getattr(self, 'farm', None):
            result['goal_blocks'] = [bool(self.scalar(f'execute if block {x} {y} {z} minecraft:{name}', success=True))
                                     for x, y, z, name in self.farm['goal_blocks']]
        if getattr(self, 'navigation', None):
            if not self.scalar('execute if entity Bench_Owner', success=True):
                raise RuntimeError('Fixture owner disconnected')
            result['target_position'] = [self.scalar(f'data get entity Bench_Owner Pos[{i}] 1000') / 1000 for i in range(3)]
        return result


def achieved(task, initial, current):
    if task.get('farm'):
        return bool(current.get('goal_blocks')) and all(current['goal_blocks'])
    item = task['item']
    if task.get('return_to_start') and math.dist(initial['position'], current['position']) > 1:
        return False
    return current['inventory'].get(item, 0) - initial['inventory'].get(item, 0) >= task['count']


def stable(a, b):
    return a['inventory'] == b['inventory'] and math.dist(a['position'], b['position']) <= 0.5
