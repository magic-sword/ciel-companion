"""Task-vs-chat routing benchmark: does an owner utterance during play move the body?

Runs the agent's own code against the shared local model and records the body actions it would
take. Nothing is executed in a world: game tools, work submission and stop are recorded and
answered with a neutral acknowledgement.

Systems
  intake  current host: GameIntake decides first; if it passes, the conversation model answers
          with the tools the pipeline exposes after an intake check.
  mind    the conversation model answers directly with the tools the pipeline exposes, without a
          separate intake decision.
The case file and labels are described in intent_routing_build.py.
"""
import argparse
import asyncio
import copy
import hashlib
import inspect
import json
import os
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAMILY = {
    'minecraft_come_here': 'come', 'minecraft_follow_me': 'follow', 'minecraft_go_to_place': 'goto',
    'minecraft_find_blocks': 'find', 'minecraft_give_item': 'give', 'minecraft_dig_down': 'dig',
    'minecraft_stop_moving': 'stop', 'stop_game_task': 'stop', 'submit_game_task': 'work', 'answer_game_task': 'answer',
}
READ_ONLY = {'game_task_status', 'current_time', 'minecraft_look_around', 'minecraft_look_at_view',
             'minecraft_facts', 'minecraft_search'}
NOW = '[今：2026年11月13日（金）・夜・秋（日本時間）]'
BODY = ('[マイクラの様子]\nシエル：体力 20/20・空腹 20/20・持ち物 なし・していること {doing}\n時刻：夜（敵が出る）\n'
        '近く：magic_sword（持ち主） 3 ブロック\n足元：grass_block\n近くのブロック：oak_log×12、grass_block×40、dirt×30')


def setup(source: Path, llm_url: str):
    sys.path.insert(0, str(source))
    os.environ['CIEL_LLM_BACKEND'] = 'local'
    os.environ['CIEL_LOCAL_LLM_URL'] = llm_url
    os.environ.setdefault('CIEL_MODEL', 'pipeline')


class World:
    """A recorded-only game environment built from the body's real MCP catalog."""

    def __init__(self, catalog, function_tool):
        self.profile = copy.deepcopy(catalog['profile'])
        # Pointing capture needs a live body; routing is decided from words and conversation here.
        self.profile['reference_context'] = False
        self.instructions = catalog.get('play', '')
        self.meta = {t['name']: dict(t.get('_meta') or {}) for t in catalog['tools']}
        self.calls = []
        self._connection_epoch = 1
        self._body = {}
        self.state = {}
        self.tools = []
        for t in catalog['tools']:
            if self.meta[t['name']].get('ciel/role') in ('act', 'look', 'know'):
                self.tools.append(self._wrap(function_tool, t['name'], t.get('description') or '',
                                             t.get('inputSchema') or {'type': 'object', 'properties': {}}))

    def _wrap(self, function_tool, name, description, schema):
        async def impl(raw_arguments: dict) -> str:
            return json.dumps(await self.use(name, raw_arguments or {}), ensure_ascii=False)
        return function_tool(impl, raw_schema={'name': name, 'description': description, 'parameters': schema})

    def playing(self):
        return True

    async def _refresh(self):
        return True

    async def use(self, name, arguments):
        self.calls.append((name, copy.deepcopy(arguments)))
        return {'status': 'accepted'}

    def tool_ids(self, *roles):
        return frozenset(n for n, m in self.meta.items() if m.get('ciel/role') in roles)


class Runner:
    def __init__(self, env, work_state):
        self.env, self.calls = env, []
        self.work = {'state': 'running', 'capability': 'minecraft.pursue_goal'} if work_state == 'running' else None

    def status(self):
        return {'state': self.work['state'], 'capability': self.work['capability']} if self.work else {}

    def body_step(self):
        return None

    async def start(self, name, arguments, **kwargs):
        self.calls.append(('submit_game_task', {'capability': name, 'arguments': copy.deepcopy(arguments)}))
        return {'task_id': 'recorded-only', 'status': 'accepted'}

    async def stop(self):
        self.calls.append(('stop_game_task', {}))
        return {'status': 'stopped'}

    async def answer(self, decision_id, action):
        self.calls.append(('answer_game_task', {'decision_id': decision_id, 'action': action}))
        return {'status': 'accepted'}


class Harness:
    def __init__(self, catalog, llm_url):
        from livekit.agents import function_tool, llm
        from livekit.agents.llm import utils as lk_utils
        import agent as agent_mod
        import capabilities as capabilities_mod
        import mind as mind_mod
        import persona as persona_mod
        import tools as tools_mod
        self.llm, self.lk_utils, self.function_tool = llm, lk_utils, function_tool
        self.agent_mod, self.mind_mod, self.tools_mod = agent_mod, mind_mod, tools_mod
        self.capabilities_mod = capabilities_mod
        self.persona = persona_mod.load_persona()
        self.catalog_json = catalog
        self.base = llm_url.rsplit('/v1', 1)[0]

    # ---- the conversation model, as the pipeline exposes it ----
    def _agent(self, world):
        catalog = self.capabilities_mod.CapabilityCatalog(self.tools_mod.MODULES)
        catalog.instructions = {'game': '\n\n'.join(p for p in (self.persona.game_instructions, world.instructions) if p)}
        catalog.bind_external(world.tools, 'game')
        fake = types.SimpleNamespace(persona=self.persona, grown='', capabilities=catalog, game=world)
        fake._presence_text = lambda pr: self.agent_mod.Ciel._presence_text(fake, pr)
        fake._talk_text = lambda t: self.agent_mod.Ciel._talk_text(fake, t)
        fake._game_text = lambda: self.agent_mod.Ciel._game_text(fake)
        return fake, catalog

    def _schema(self, fn):
        raw = getattr(getattr(fn, 'info', None), 'raw_schema', None)
        return {'type': 'function', 'function': raw if raw else self.lk_utils.build_legacy_openai_schema(fn)['function']}

    def _post(self, body):
        req = urllib.request.Request(self.base + '/v1/chat/completions', json.dumps(body).encode(),
                                     {'Content-Type': 'application/json', 'X-Ciel-Work-Class': 'foreground'})
        for attempt in range(6):
            try:
                return json.loads(urllib.request.urlopen(req, timeout=300).read())
            except urllib.error.HTTPError as error:
                # The shared API answers 503 while another job holds it; that is not the model's decision.
                if error.code != 503 or attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))

    def _context(self, case, system):
        llm = self.llm
        c = llm.ChatContext()
        c.add_message(role='system', content=system)
        for role, text in case['context']:
            c.add_message(role=role, content=text)
        doing = '原木を集めている' if case['work'] == 'running' else 'なし'
        c.add_message(role='system', content=NOW + '\n\n' + BODY.format(doing=doing))
        c.add_message(role='user', content=case['text'])
        return c

    async def mind(self, case, world, *, after_intake):
        fake, catalog = self._agent(world)
        eligible = list(self.tools_mod.goals.TOOLS) + list(self.tools_mod.clock.TOOLS) + list(world.tools) \
            + [catalog.loader, catalog.executor]
        if after_intake:
            eligible = [fn for fn in eligible if fn.id not in self.mind_mod.GOAL_MOVING]
        visible = catalog.select(eligible)
        system = self.agent_mod.Ciel.instructions_for(fake, 'normal', 'solo') + '\n\n' + catalog.summary()
        wire = self.mind_mod.local_context(self._context(case, system)).to_provider_format('openai')[0]
        actions, text, rounds = [], '', 0
        while rounds < 3:
            rounds += 1
            tools = [self._schema(fn) for fn in visible]
            choice = self._post({'model': 'local', 'messages': wire, 'tools': tools, 'max_tokens': 300,
                                 'chat_template_kwargs': {'enable_thinking': False}})['choices'][0]['message']
            text = choice.get('content') or ''
            calls = choice.get('tool_calls') or []
            if not calls:
                break
            wire = wire + [{'role': 'assistant', 'content': text, 'tool_calls': calls}]
            moved = False
            for call in calls:
                name = call['function']['name']
                try:
                    args = json.loads(call['function'].get('arguments') or '{}')
                except ValueError:
                    args = {}
                target = args.get('tool_id') if name == catalog.executor.id else name
                if name == catalog.loader.id:
                    result = catalog.load(args.get('service_ids'))
                elif target in READ_ONLY:
                    result = {'status': 'idle'}
                elif name == catalog.executor.id and not (isinstance(target, str) and catalog.can_execute(target)):
                    # The host rejects an unloaded or unknown tool id before anything runs.
                    result = {'status': 'not_loaded'}
                else:
                    actions.append((target, args.get('arguments', args) if name == catalog.executor.id else args))
                    result = {'status': 'accepted'}
                    moved = True
                wire.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result, ensure_ascii=False)})
            if moved:
                break
            visible = catalog.select(eligible)
        return actions, text, rounds

    def _intake(self, world, work):
        from game_intake import GameIntake
        runner = Runner(world, work)
        p = self.persona
        return runner, GameIntake(runner, p.game_intake_instructions, select_instructions=p.game_select_instructions,
                                  draft_instructions=p.game_draft_instructions)

    # ---- the current intake ----
    async def intake(self, case, world):
        runner, intake = self._intake(world, case['work'])
        decision = {}
        infer = intake._infer

        async def capture(payload, started):
            try:
                value = await infer(payload, started)
            except Exception as error:
                decision.setdefault('errors', []).append(f"{payload['stage']}:{type(error).__name__}")
                raise
            if payload['stage'] == 'select':
                decision.update(value)
            else:
                decision['arguments_operation'] = value.get('operation')
            return value
        intake._infer = capture
        try:
            item = self.llm.ChatMessage(id=case['id'], role='user', content=[case['text']])
            # Sources that read the conversation receive the same turns the conversation model sees.
            if 'conversation' in inspect.signature(intake.handle).parameters:
                reply = await intake.handle(item, conversation=[tuple(c) for c in case['context']])
            else:
                reply = await intake.handle(item)
        finally:
            await intake.close()
        return reply, decision, runner.calls

    async def run(self, case, system):
        world = World(self.catalog_json, self.function_tool)
        began = time.monotonic()
        row = {'id': case['id'], 'system': system}
        if system == 'intake':
            reply, decision, runner_calls = await self.intake(case, world)
            row['intake'] = {'operation': decision.get('operation'), 'capability': decision.get('capability'),
                             'speaker_act': decision.get('speaker_act'),
                             'errors': decision.get('errors', []), 'reply': reply}
            actions = runner_calls + world.calls
            if reply is None:
                world.calls = []
                more, text, rounds = await self.mind(case, world, after_intake=True)
                actions += more
                row.update(reply=text, rounds=rounds)
            else:
                row.update(reply=reply, rounds=0)
        else:
            actions, text, rounds = await self.mind(case, world, after_intake=False)
            row.update(reply=text, rounds=rounds)
        row['actions'] = [[n, a] for n, a in actions]
        row['seconds'] = round(time.monotonic() - began, 2)
        row.update(score(case, row['actions']))
        return row


def families(actions):
    return [FAMILY.get(name, 'other') for name, _ in actions if name not in READ_ONLY]


def score(case, actions):
    got = families(actions)
    moved = [f for f in got if f not in ('stop', 'answer')]
    stopped = 'stop' in got
    expect = case['expect']
    if expect == 'any':
        verdict = 'unscored'
    elif expect == 'chat':
        verdict = 'ok' if not got else ('false_move' if moved else 'false_stop' if stopped else 'false_other')
    elif expect == 'stop':
        verdict = 'ok' if stopped and not moved else ('missed' if not got else 'wrong')
    else:
        if not moved:
            verdict = 'missed'
        else:
            verdict = 'ok' if moved[0] in case['families'] and len(moved) == 1 else 'wrong'
    return {'families': got, 'verdict': verdict}


def summarize(rows, cases):
    by_id = {c['id']: c for c in cases}
    out = {}
    for system in sorted({r['system'] for r in rows}):
        rs = [r for r in rows if r['system'] == system]
        s = {}
        for split in sorted({by_id[r['id']]['split'] for r in rs}):
            part = [r for r in rs if by_id[r['id']]['split'] == split]
            chat = [r for r in part if by_id[r['id']]['expect'] == 'chat']
            act = [r for r in part if by_id[r['id']]['expect'] in ('move', 'stop')]
            s[split] = {
                'scored': sum(r['verdict'] != 'unscored' for r in part),
                'accuracy': round(sum(r['verdict'] == 'ok' for r in part) / max(1, sum(r['verdict'] != 'unscored' for r in part)), 3),
                'chat_cases': len(chat), 'chat_false_action': sum(r['verdict'].startswith('false') for r in chat),
                'request_cases': len(act), 'request_missed': sum(r['verdict'] == 'missed' for r in act),
                'request_wrong_action': sum(r['verdict'] == 'wrong' for r in act),
                'mean_seconds': round(sum(r['seconds'] for r in part) / max(1, len(part)), 2),
            }
        out[system] = s
    return out


def load_cases(splits):
    cases = json.loads((HERE / 'intent_routing_cases.json').read_text(encoding='utf-8'))
    real = HERE.parents[1] / '.local/intent-routing/real_cases.json'
    if 'real' in splits:
        if not real.exists():
            raise SystemExit('recorded cases are missing; run intent_routing_build.py with the recorded utterances')
        cases += json.loads(real.read_text(encoding='utf-8'))
    return [c for c in cases if c['split'] in splits]


async def main(args):
    setup(args.agent_source, args.llm_url)
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    cases = load_cases(args.split)
    if args.case:
        cases = [c for c in cases if c['id'] in args.case]
    harness = Harness(catalog, args.llm_url)
    rows = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for system in args.system:
        for repeat in range(args.repeat):
            for case in cases:
                try:
                    row = await harness.run(case, system)
                except Exception as error:
                    row = {'id': case['id'], 'system': system, 'error': f'{type(error).__name__}: {error}'[:300],
                           'actions': [], 'families': [], 'verdict': 'error', 'seconds': 0}
                row['repeat'] = repeat
                rows.append(row)
                print(json.dumps({k: row.get(k) for k in ('system', 'id', 'verdict', 'families', 'seconds')}, ensure_ascii=False), flush=True)
                report = {'suite': 'intent-routing-v1', 'agent_source': str(args.agent_source),
                          'cases_sha256': hashlib.sha256((HERE / 'intent_routing_cases.json').read_bytes()).hexdigest(),
                          'catalog_sha256': hashlib.sha256(args.catalog.read_bytes()).hexdigest(),
                          'rows': rows, 'summary': summarize(rows, cases)}
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summarize(rows, cases), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--system', action='append', choices=['intake', 'mind'], required=True)
    parser.add_argument('--split', action='append', choices=['dev', 'real'], default=None)
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--catalog', type=Path, required=True, help='Body MCP catalog: {profile, tools, play}')
    parser.add_argument('--agent-source', type=Path, default=HERE.parent / 'agent')
    parser.add_argument('--llm-url', default=os.environ.get('CIEL_BENCH_LLM_URL', 'http://127.0.0.1:8094/v1'))
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    a.split = a.split or ['dev']
    asyncio.run(main(a))
