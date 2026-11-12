"""Add the isolated development bot to the existing offline server whitelist."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import uuid


def configure(prod):
    prod=prod.resolve()
    values={}
    for line in (prod/'.env.minecraft').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            name,value=line.split('=',1);values[name.strip()]=value.strip().strip('\"\'')
    if values.get('MINECRAFT_EULA','').upper()!='TRUE' or not values.get('MC_OWNER'):
        raise RuntimeError('Existing Minecraft consent and owner are required')
    data=prod/'minecraft/data'
    properties=dict(line.split('=',1)for line in (data/'server.properties').read_text().splitlines()if '='in line and not line.startswith('#'))
    if properties.get('online-mode')!='false' or properties.get('white-list')!='true':
        raise RuntimeError('Development bot requires the existing offline whitelisted server')
    path=data/'whitelist.json'
    current=json.loads(path.read_text())
    name='Ciel_Debug'
    identity=str(uuid.UUID(bytes=hashlib.md5(('OfflinePlayer:'+name).encode()).digest(),version=3))
    if any(row.get('name')==name and row.get('uuid')!=identity for row in current):
        raise RuntimeError('Conflicting development player identity')
    if not any(row.get('uuid')==identity for row in current):
        backup=data/'ciel-config-backups';backup.mkdir(exist_ok=True)
        shutil.copy2(path,backup/f'whitelist-{time.time_ns()}.json')
        temp=path.with_name('whitelist.dev.tmp')
        temp.write_text(json.dumps([*current,{'name':name,'uuid':identity}],indent=2)+'\n')
        temp.chmod(path.stat().st_mode);temp.replace(path)
    subprocess.run(['docker','exec','ciel-minecraft-1','rcon-cli','whitelist','reload'],check=True)
    print('Debug player whitelist ready: Ciel_Debug')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prod-dir',type=Path,required=True)
    configure(parser.parse_args().prod_dir)
