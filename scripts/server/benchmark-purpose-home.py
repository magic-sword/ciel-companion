"""Run purpose/prefix checks on the shared API without changing any service."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('continuation_home',Path(__file__).with_name('benchmark-continuation-home.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__=='__main__':
    raise SystemExit(module.main('server/benchmark/purpose_cache.py'))
