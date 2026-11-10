#!/usr/bin/env python3
"""Control only the dedicated voice evaluation workers; see voice-benchmark-ja.md."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess

spec=importlib.util.spec_from_file_location('home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reuse','start','stop','live','proxy-start','proxy-stop','contention'])
    parser.add_argument('--variant',choices=['baseline','fast'],default='fast')
    parser.add_argument('--corpus-run',default='20261110T020907Z')
    parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--tag')
    args=parser.parse_args()
    command=['python3','work/ciel-voice-evaluation/server/stt/voice_fast_home.py',args.action,
             '--variant',args.variant,'--corpus-run',args.corpus_run,'--rounds',str(args.rounds)]
    if args.smoke:command.append('--smoke')
    if args.tag:command += ['--tag',args.tag]
    raise SystemExit(subprocess.run(home.ssh_args()+[shlex.join(command)]).returncode)
