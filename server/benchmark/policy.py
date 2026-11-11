"""Practical deadlines and evidence of progress; never an LLM judge."""
import json
import math
import re

VERSION = 'practical-v1'
DEFAULT = {'seconds':90, 'first_action':30, 'no_progress':30, 'same_failure':2,
           'blocked_grace':10, 'stop_grace':5}
ACTION_TOOLS = {'minecraft_pointed_action','minecraft_clear_region','minecraft_build_region','minecraft_collect_blocks','minecraft_goal_step','minecraft_craft_item',
                'minecraft_prepare_region',
                'minecraft_give_item','minecraft_go_to_place','minecraft_follow_me',
                'minecraft_come_here','minecraft_find_blocks','minecraft_dig_down','minecraft_look_around'}
CONSTRAINT = r'(原木|木材|木|材料|作業台|道具|資源).{0,40}(不足|見つから|見当たら|ありません|無い|ない|足り|用意でき)'
DECLINE = r'(できません|作れません|続けられません|作るのは難しい|製作は難しい|中止します|断念します|停止します|作業を止めます)'


def budget(task, cap=None):
    result = {**DEFAULT, **task.get('budget',{})}
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v <= 0
           for v in result.values()):
        raise ValueError('Task budgets must be finite and positive')
    if set(result) != set(DEFAULT):
        raise ValueError('Unknown task budget field')
    if cap is not None:
        result['seconds'] = min(result['seconds'],cap)
    return result


class Progress:
    def __init__(self, initial, task):
        self.task = task
        self.highwater = dict(initial['inventory'])
        self.cells = {self.cell(initial)}
        self.last_progress = 0
        self.first_action = None
        self.calls = {}
        self.pending = set()
        self.completed = set()
        self.failures = {}
        self.failure_ids = set()
        self.decline = None
        self.decline_at = None
        self.resumed_after_decline = False
        self.region_distance = self.distance_to_region(initial) if task.get('region_spec') else None

    def distance_to_region(self,state):
        rows=self.task.get('spatial',{}).get('expected',[])
        return min((math.dist(state['position'],[x+.5,y+.5,z+.5]) for x,y,z,_ in rows),default=0)

    @staticmethod
    def cell(state):
        return tuple(math.floor(x/2) for x in state['position'])

    def observe(self, state, elapsed):
        if self.region_distance is not None:
            distance=self.distance_to_region(state)
            if distance < self.region_distance-.5:
                self.region_distance=distance
                self.last_progress=elapsed
            return
        cell = self.cell(state)
        progress = cell not in self.cells
        self.cells.add(cell)
        for item,count in state['inventory'].items():
            if count > self.highwater.get(item,0):
                progress = True
                self.highwater[item] = count
        if progress:
            self.last_progress = elapsed
            self.failures.clear()

    def failure(self, identity, signature, reason):
        if identity not in self.failure_ids:
            self.failure_ids.add(identity)
            key = (signature,reason)
            self.failures[key] = self.failures.get(key,0)+1

    def event(self, e, elapsed):
        if e['kind'] == 'work_action':
            e = {**e, 'kind': 'game_call', 'name': 'minecraft_work_step'}
        elif e['kind'] == 'work_action_result':
            e = {**e, 'kind': 'game_result'}
        kind = e['kind']
        if kind == 'game_call':
            args = {k:v for k,v in e.get('arguments',{}).items() if k!='request_id'}
            signature = (e.get('name'),json.dumps(args,sort_keys=True,ensure_ascii=False))
            self.calls[e.get('id')] = signature
            if e.get('name') in ACTION_TOOLS or e.get('name') == 'minecraft_work_step':
                if self.first_action is None:
                    self.first_action = elapsed
                if self.decline is not None:
                    self.resumed_after_decline = True
            self.pending.add(('call',e.get('id')))
        elif kind == 'game_result':
            identity = e.get('id')
            self.pending.discard(('call',identity))
            result = e.get('result',{})
            signature = self.calls.get(identity)
            if result.get('ok') is False or result.get('status') in ('error','refused','unavailable','no_answer','busy'):
                self.failure(('call',identity),signature,result.get('reason') or result.get('status'))
            if result.get('status') in ('started','accepted') and result.get('task') is not None:
                task_id = str(result.get('session',''))+':'+str(result['task'])
                if task_id not in self.completed:
                    self.pending.add(('task',task_id))
                self.calls[('task',task_id)] = signature
        elif kind == 'game_task_result':
            identity = e.get('id')
            self.pending.discard(('task',identity))
            self.completed.add(identity)
            if not e.get('ok') and e.get('reason'):
                signature = self.calls.get(('task',identity)) or ('task_title',e.get('title') or identity)
                self.failure(('task',identity),signature,e['reason'])
        elif kind == 'item' and e.get('role')=='assistant' and not e.get('interrupted'):
            text = e.get('text','')
            patterns = self.task.get('report_patterns',[CONSTRAINT,DECLINE])
            if all(re.search(p,text,re.S) for p in patterns) and not re.search(r'(もし|場合は|としたら)',text):
                self.decline = text
                self.decline_at = elapsed
                self.resumed_after_decline = False

    def idle(self, goal):
        return not self.pending and goal.get('state') not in ('accepted','running','cancelling')

    def reason(self, elapsed, limits):
        if self.first_action is None and elapsed >= limits['first_action']:
            return 'first_action_timeout'
        if max(self.failures.values(),default=0) >= limits['same_failure']:
            return 'repeated_failure'
        if elapsed-self.last_progress >= limits['no_progress']:
            return 'no_progress'
        return None
