"""Body-layer tasks whose goal and success condition come from vendored Mindcraft task files.

A suite entry names the upstream file and task id. The upstream definition owns the goal
text, target item, count and initial inventory; CIEL owns the arena (with any ore blocks),
the deadline under the task's policy (practical-v1 or long-horizon-v1) and the milestone list
used for partial progress. Only single-agent inventory
(techtree) tasks without blocked commands or missing items are accepted.
"""
import hashlib
import json
from pathlib import Path

from .farm import progress as farm_progress

VENDOR = Path(__file__).resolve().parents[1]/'minecraft'/'src'/'vendor'/'mindcraft'
OWNED = ('prompt', 'item', 'count', 'inventory', 'action', 'spec')


def _inventory(value):
    value = value or {}
    if value and all(key.isdigit() for key in value):
        if set(value) != {'0'}:
            raise ValueError('Mindcraft task gives inventory to several agents')
        value = value['0']
    if not all(isinstance(k, str) and isinstance(v, int) and v > 0 for k, v in value.items()):
        raise ValueError('Invalid Mindcraft initial inventory')
    return dict(value)


def expand(task, vendor=VENDOR):
    ref = task.get('mindcraft')
    if ref is None:
        return task
    if not isinstance(ref, dict) or set(ref) != {'file', 'task'}:
        raise ValueError('mindcraft must be {"file", "task"}')
    if any(key in task for key in OWNED):
        raise ValueError('Mindcraft tasks take goal, target, count and inventory from upstream')
    if 'conversation' in task.get('modes', ['body']):
        raise ValueError('Mindcraft goals are English body inputs; write a Japanese conversation task separately')
    root = Path(vendor).resolve()
    path = (root/ref['file']).resolve()
    if not ref['file'].startswith('tasks/') or root not in path.parents:
        raise ValueError('Mindcraft task file must be under the vendored tasks directory')
    upstream = json.loads(path.read_text(encoding='utf-8'))[ref['task']]
    if upstream.get('agent_count', 1) != 1 or upstream.get('type', 'techtree') != 'techtree':
        raise ValueError('Only single-agent techtree tasks are supported')
    if any((upstream.get('blocked_actions') or {}).get('0', [])) or upstream.get('missing_items'):
        raise ValueError('Blocked commands and missing items are not supported')
    target, count = upstream['target'], upstream.get('number_of_target', 1)
    if not isinstance(target, str) or not isinstance(count, int) or count <= 0:
        raise ValueError('Only one target item with an integer count is supported')
    inventory = _inventory(upstream.get('initial_inventory'))
    if target in inventory:
        raise ValueError('Upstream counts absolute inventory; the target must start at zero')
    if target not in task.get('milestones', []):
        raise ValueError('Milestones must end with the upstream target')
    canonical = json.dumps(upstream, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return {**task, 'modes': task.get('modes', ['body']), 'prompt': upstream['goal'], 'item': target,
            'count': count, 'inventory': inventory,
            'upstream': {'file': ref['file'], 'task': ref['task'], 'sha256': hashlib.sha256(canonical).hexdigest(),
                         'timeout': upstream.get('timeout'), 'validator': 'inventory_count'}}


def progress(task, observed, initial, final):
    """Partial progress beside the binary result. Milestones are a lower bound: a short-lived
    intermediate can be crafted and consumed between two snapshots, so achieving the target
    credits every milestone."""
    if task.get('farm') or task.get('house'):
        target = farm_progress(final.get('goal_blocks'))
    else:
        gained = final['inventory'].get(task['item'], 0) - initial['inventory'].get(task['item'], 0)
        target = max(0.0, min(1.0, gained/task['count']))
    milestones = task['milestones']
    reached = len(milestones) if target >= 1 else len(set(observed) & set(milestones))
    return {'target': round(target, 3), 'milestones': round(reached/len(milestones), 3) if milestones else None,
            'milestones_reached': reached, 'milestones_total': len(milestones)}
