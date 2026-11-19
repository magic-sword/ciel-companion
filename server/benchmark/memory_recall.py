"""Offline recall benchmark: which stored memories reach the conversation model for a turn.

Stage 0 of docs/services/associative-memory-ja.md. Deterministic except --retriever mind (an LLM picks): no DB, no game.
It measures retrieval (what is put in front of the model), not whether Ciel then says it.

Run from the repository root:
  .venv/Scripts/python.exe -B -X utf8 server/benchmark/memory_recall.py score --retriever current --out <report.json>
  .venv/Scripts/python.exe -B -X utf8 server/benchmark/memory_recall.py score --retriever recall [--embedder NAME] [--keys KEYS.json] --out <report.json>
  .venv/Scripts/python.exe -B -X utf8 server/benchmark/memory_recall.py score --retriever mind --llm-url URL [--thinking] [--embedder NAME] [--keys KEYS.json] --out <report.json>
  .venv/Scripts/python.exe -B -X utf8 server/benchmark/memory_recall.py write-keys --llm-url URL --out KEYS.json
  .venv/Scripts/python.exe -B -X utf8 server/benchmark/memory_recall.py compare <base.json> <candidate.json>
"""
import argparse
import ast
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SUITE = Path(__file__).with_name('memory_recall_cases.json')
AGENT = ROOT / 'server/agent'
sys.path.insert(0, str(AGENT))
import recall  # noqa: E402  (the same eligibility and ranking as the host)

# Neutral filler: distinct, and unrelated to every case topic (rest, base, song, zombie, village, house, ...).
NOTE_SUBJECTS = ['好きな果物', '好きな色', '好きな花', '好きな文房具', '好きなお菓子', '好きな飲み物',
                 'よく使うかばん', '好きな季節', '朝ごはん', '好きな数字']
NOTE_VALUES = ['りんご', '緑', 'ひまわり', '青いペン', 'クッキー', '麦茶', '黒いリュック', '秋', 'パン', '7']
DIARY_ACTIONS = ['クモを倒した', 'スケルトンを倒した', '高い所から落ちて倒れた', '羊の毛を刈った', '花を摘んだ',
                 'ほっぺをつつかれた', '肩をとんとんされた', '鶏を見かけた', '雨宿りをした', '砂を集めた',
                 '石のつるはしを作った', '松明を置いた']


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_suite(path: Path = SUITE) -> dict:
    suite = json.loads(path.read_text(encoding='utf-8'))
    ids = [c['id'] for c in suite['cases']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate case IDs')
    for c in suite['cases']:
        known = {m['id'] for m in c['memories']}
        for key in ('relevant', 'past', 'forbidden'):
            missing = set(c['expect'].get(key, [])) - known
            if missing:
                raise ValueError(f'{c["id"]}: {key} refers to unknown memories {sorted(missing)}')
    return suite


@dataclass
class Memory:
    id: str
    kind: str          # note / diary / like / game_place / game_event
    text: str
    at: datetime
    person: str | None = None
    world: str | None = None
    ref: str | None = None
    invalidated_at: datetime | None = None
    filler: bool = False


@dataclass
class Context:
    now: datetime
    presence: str      # solo / close / public
    speaker: str | None
    world: str | None
    turns: list
    people: dict = field(default_factory=dict)


@dataclass
class Item:
    id: str
    channel: str       # auto: put in front of the model; tool: only through a tool the model must call
    past: bool = False
    recalled: bool = False   # chosen by relevance for this turn (not pushed regardless of the topic)


def build_case(suite: dict, case: dict) -> tuple[list[Memory], Context]:
    now = datetime.fromisoformat(suite['now'])
    ago = lambda days: now - timedelta(days=days)
    memories = [Memory(id=m['id'], kind=m['kind'], text=m['text'], at=ago(m['days_ago']), person=m.get('person'),
                       world=m.get('world'), ref=m.get('ref'),
                       invalidated_at=ago(m['invalidated_days_ago']) if m.get('invalidated_days_ago') is not None else None)
               for m in case['memories']]
    by_id = {m.id: m for m in memories}
    note_pool = [f'{s}は{v}' for s in NOTE_SUBJECTS for v in NOTE_VALUES]
    used = {'note': 0, 'diary': 0}
    for spec in case.get('filler', []):
        kind = spec['kind']
        anchor = by_id[spec['around']].at if spec.get('around') else now - timedelta(days=30)
        span_new = (now - anchor).total_seconds()
        for side, count in (('newer', spec['newer']), ('older', spec['older'])):
            for i in range(count):
                if side == 'newer':
                    at = anchor + timedelta(seconds=span_new * (i + 1) / (count + 1))
                else:
                    at = anchor - timedelta(days=(i + 1) * 0.5)
                n = used[kind]
                used[kind] += 1
                text = note_pool[(n * 7) % len(note_pool)] if kind == 'note' else \
                    f'{DIARY_ACTIONS[n % len(DIARY_ACTIONS)]}（{n + 1}回目）'
                memories.append(Memory(id=f'fill_{kind}_{n}', kind=kind, text=text, at=at,
                                       person=spec.get('person'), filler=True))
    ctx = case['context']
    return memories, Context(now=now, presence=ctx['presence'], speaker=ctx.get('speaker'), world=ctx.get('world'),
                             turns=ctx['turns'], people=suite.get('people', {}))


def module_constants(path: Path, names: set[str]) -> dict:
    """Read integer constants from the agent source without importing its runtime dependencies."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in names and isinstance(node.value, ast.Constant):
                found[node.targets[0].id] = node.value.value
    missing = names - set(found)
    if missing:
        raise ValueError(f'{path.name}: constants not found {sorted(missing)}')
    return found


class CurrentMethod:
    """What the host does today (speakers.py, speaker_store.py, diary.py, growth.py, agent.py):
    - the identified speaker's notes: storage keeps the newest MAX_NOTES; in solo/close the newest PUSH_NOTES
      are pushed into the turn; the whole stored set is reachable only through recall_about_speaker.
      In public nothing is pushed. Other people's notes never reach this speaker's turn.
    - Ciel's likes: all of them are in the instructions.
    - Ciel's diary (ciel_events): stored, but only the growth job reads it; the conversation never sees it.
    - Minecraft base / saved places live in the body; game milestones other than kills are not recorded.
    The speaker is assumed identified with consent, so this is the best case for today's method."""
    id = 'current'

    def __init__(self):
        speakers = module_constants(AGENT / 'speakers.py', {'PUSH_NOTES'})
        store = module_constants(AGENT / 'speaker_store.py', {'MAX_NOTES'})
        self.push_notes, self.max_notes = speakers['PUSH_NOTES'], store['MAX_NOTES']
        self.config = {'PUSH_NOTES': self.push_notes, 'MAX_NOTES': self.max_notes}

    def retrieve(self, memories: list[Memory], ctx: Context) -> list[Item]:
        items = []
        if ctx.speaker:
            own = sorted((m for m in memories if m.kind == 'note' and m.person == ctx.speaker), key=lambda m: m.at)
            stored = own[-self.max_notes:]
            pushed = stored[-self.push_notes:] if ctx.presence in ('solo', 'close') else []
            pushed_ids = {m.id for m in pushed}
            items += [Item(m.id, 'auto') for m in pushed]
            items += [Item(m.id, 'tool') for m in stored if m.id not in pushed_ids]
        items += [Item(m.id, 'auto') for m in sorted(memories, key=lambda m: m.at) if m.kind == 'like']
        return items


class RecallMethod(CurrentMethod):
    """今の渡し方（最近のメモ・好み）に、関連性で思い出したこと（server/agent/recall.py）を足す。
    鍵は write-keys で会話サーバーと同じ指示から書いたもの（無ければ鍵なし）、埋め込みは --embedder のモデル"""
    id = 'recall'

    def __init__(self, embedder=None, keys: dict | None = None):
        super().__init__()
        self.embedder, self.keys = embedder, keys or {}
        self._vectors = {}
        self.config = {**self.config, 'embedder': getattr(embedder, 'name', '') or None,
                       'keys': len(self.keys), 'top_k': recall.TOP_K, 'min_relevance': recall.MIN_RELEVANCE,
                       'cosine_floor': recall.COSINE_FLOOR}

    def _vector(self, text: str, query: bool):
        if self.embedder is None:
            return None
        key = (text, query)
        if key not in self._vectors:
            self._vectors[key] = self.embedder.embed([text], query=query)[0]
        return self._vectors[key]

    def candidate(self, m: Memory):
        keys = self.keys.get(m.text, '')
        doc = recall.document(recall.Candidate(id=m.id, kind=m.kind, text=m.text, at=m.at, keys=keys))
        return recall.Candidate(id=m.id, kind=m.kind, text=m.text, at=m.at, keys=keys, person_id=m.person,
                                world=m.world, ref=m.ref, invalidated_at=m.invalidated_at,
                                importance=4 if m.kind == 'game_place' else 3, embedding=self._vector(doc, False))

    def retrieve(self, memories: list[Memory], ctx: Context) -> list[Item]:
        items = super().retrieve(memories, ctx)
        pool = [self.candidate(m) for m in memories if m.kind != 'like']
        query = ' '.join(t['text'] for t in ctx.turns if t['role'] == 'user')
        situation = recall.Situation(presence=ctx.presence, person_id=ctx.speaker, world=ctx.world)
        got = recall.rank(pool, situation, query, self._vector(query, True), ctx.now)
        auto = {i.id for i in items if i.channel == 'auto'}
        recalled = [Item(r.id, 'auto', past=r.past, recalled=True) for r in got if r.id not in auto]
        return recalled + [i for i in items if i.id not in {r.id for r in recalled}]


class MindMethod(RecallMethod):
    """System 2 variant: the same search proposes a wider list, then an LLM (the mind) picks what matters.
    Experimental (prompts/recall_mind.md). The latency of each LLM call is recorded."""
    id = 'mind'
    PROMPT = Path(__file__).with_name('prompts') / 'recall_mind.md'
    POOL = 8
    POOL_MIN = 0.2

    def __init__(self, embedder=None, keys=None, llm_url='', model='local', thinking=False):
        super().__init__(embedder, keys)
        self.llm_url, self.model, self.thinking = llm_url.rstrip('/'), model, thinking
        self.instructions = self.PROMPT.read_text(encoding='utf-8')
        self.calls: list[dict] = []
        self.config = {**self.config, 'llm': model, 'thinking': thinking, 'pool': self.POOL, 'pool_min': self.POOL_MIN,
                       'prompt_sha256': hashlib.sha256(self.instructions.encode()).hexdigest()}

    def retrieve(self, memories, ctx):
        import time
        import httpx
        items = CurrentMethod.retrieve(self, memories, ctx)
        pool = [self.candidate(m) for m in memories if m.kind != 'like']
        query = ' '.join(t['text'] for t in ctx.turns if t['role'] == 'user')
        situation = recall.Situation(presence=ctx.presence, person_id=ctx.speaker, world=ctx.world)
        got = recall.rank(pool, situation, query, self._vector(query, True), ctx.now, k=self.POOL, min_relevance=self.POOL_MIN)
        chosen = []
        if got:
            request = {'now': f'{ctx.now:%Y-%m-%d %H:%M}',
                       'conversation': [{'speaker': ctx.people.get(ctx.speaker, '相手') if t['role'] == 'user'
                                         else 'シエル', 'text': t['text']} for t in ctx.turns],
                       'candidates': [{'id': r.id, 'when': recall.ago(r.at, ctx.now), 'text': r.text, 'past': r.past} for r in got]}
            body = {'model': self.model, 'temperature': 0, 'response_format': {'type': 'json_object'},
                    'chat_template_kwargs': {'enable_thinking': self.thinking},
                    'messages': [{'role': 'system', 'content': self.instructions},
                                 {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}]}
            t0 = time.perf_counter()
            r = httpx.post(self.llm_url + '/chat/completions', json=body, timeout=300)
            ms = (time.perf_counter() - t0) * 1000
            r.raise_for_status()
            data = r.json()
            try:
                out = json.loads(data['choices'][0]['message']['content'] or '{}')
            except ValueError:
                out = {}
            ids = {c.id for c in got}
            chosen = [i for i in out.get('use', []) if i in ids][:recall.TOP_K]
            timings = data.get('timings') or {}
            self.calls.append({'ms': round(ms, 1), 'prompt_n': timings.get('prompt_n'), 'predicted_n': timings.get('predicted_n'),
                               'thought': out.get('thought', '')})
        by_id = {r.id: r for r in got}
        auto = {i.id for i in items if i.channel == 'auto'}
        recalled = [Item(i, 'auto', past=by_id[i].past, recalled=True) for i in chosen if i not in auto]
        return recalled + [i for i in items if i.id not in {r.id for r in recalled}]


RETRIEVERS = {'current': CurrentMethod, 'recall': RecallMethod, 'mind': MindMethod}


def write_keys(suite: dict, llm_url: str, model: str = 'local') -> dict:
    """課題の記憶（埋め草も含む）に、会話サーバーと同じ指示で鍵を書く（OpenAI 互換の窓口。温度 0）"""
    import httpx
    sys.path.insert(0, str(AGENT))
    from persona import load_persona
    instructions = load_persona().memory_keys_instructions
    texts = []
    for case in suite['cases']:
        memories, _ = build_case(suite, case)
        texts += [m.text for m in memories if m.kind != 'like' and m.text not in texts]
    out = {}
    for start in range(0, len(texts), recall.KeyWriter.BATCH):
        batch = texts[start:start + recall.KeyWriter.BATCH]
        body = {'model': model, 'temperature': 0, 'response_format': {'type': 'json_object'},
                'chat_template_kwargs': {'enable_thinking': False},
                'messages': [{'role': 'system', 'content': instructions},
                             {'role': 'user', 'content': json.dumps(
                                 {'memories': [{'id': str(i), 'text': t} for i, t in enumerate(batch)]}, ensure_ascii=False)}]}
        r = httpx.post(llm_url.rstrip('/') + '/chat/completions', json=body, timeout=300)
        r.raise_for_status()
        keys = json.loads(r.json()['choices'][0]['message']['content'] or '{}').get('keys') or {}
        for i, t in enumerate(batch):
            k = keys.get(str(i))
            if isinstance(k, str) and k.strip():
                out[t] = ' '.join(k.split())[:recall.KEY_CHARS]
    return {'instructions_sha256': hashlib.sha256(instructions.encode()).hexdigest(), 'model': model, 'keys': out}


def score_case(case: dict, memories: list[Memory], items: list[Item]) -> dict:
    by_id = {m.id: m for m in memories}
    unknown = [i.id for i in items if i.id not in by_id]
    if unknown:
        raise ValueError(f'{case["id"]}: retriever returned unknown ids {unknown}')
    auto = [i for i in items if i.channel == 'auto']
    reach = {i.id for i in items}
    auto_ids = [i.id for i in auto]
    expect = case['expect']
    relevant = expect.get('relevant', [])
    past = set(expect.get('past', []))
    forbidden = set(expect.get('forbidden', []))
    ranks = {r: (auto_ids.index(r) + 1 if r in auto_ids else None) for r in relevant}
    return {
        'id': case['id'], 'stage': case['stage'], 'ability': case['ability'],
        'relevant': len(relevant),
        # None = no relevant memory exists (abstention/privacy/control): recall is not applicable, not 0 or 1.
        'recall_auto': sum(r in auto_ids for r in relevant) / len(relevant) if relevant else None,
        'recall_reach': sum(r in reach for r in relevant) / len(relevant) if relevant else None,
        'ranks': ranks,
        'forbidden_auto': sorted(i.id for i in auto if i.id in forbidden),
        # An invalidated memory is acceptable only when the retriever marks it as the past.
        'stale_as_current': sorted(i.id for i in auto if (i.id in past or by_id[i.id].invalidated_at) and not i.past),
        'past_marked': sorted(i.id for i in auto if i.id in past and i.past),
        # Relevance picks that are neither expected nor allowed context: noise the model must ignore.
        'recalled_extra': sorted(i.id for i in auto if i.recalled and i.id not in relevant and i.id not in past),
        'auto_count': len(auto),
        'auto_chars': sum(len(by_id[i.id].text) for i in auto),
    }


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def summarize(rows: list[dict]) -> dict:
    def block(sel):
        applicable = [r for r in sel if r['recall_auto'] is not None]
        return {
            'cases': len(sel),
            'recall_cases': len(applicable),
            'recall_auto': mean(r['recall_auto'] for r in sel),
            'recall_reach': mean(r['recall_reach'] for r in sel),
            'full_recall_auto': sum(r['recall_auto'] == 1 for r in applicable),
            'forbidden_auto': sum(len(r['forbidden_auto']) for r in sel),
            'stale_as_current': sum(len(r['stale_as_current']) for r in sel),
            'recalled_extra': sum(len(r.get('recalled_extra', [])) for r in sel),
            'auto_count_mean': mean(r['auto_count'] for r in sel),
            'auto_chars_mean': mean(r['auto_chars'] for r in sel),
        }
    out = {'all': block(rows)}
    for key in ('stage', 'ability'):
        for value in sorted({r[key] for r in rows}, key=str):
            out[f'{key}:{value}'] = block([r for r in rows if r[key] == value])
    return out


def git_commit() -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def run(retriever, suite: dict) -> dict:
    rows = []
    for case in suite['cases']:
        memories, ctx = build_case(suite, case)
        rows.append(score_case(case, memories, retriever.retrieve(memories, ctx)))
    return {
        'suite': suite['version'], 'suite_sha256': digest(suite), 'retriever': retriever.id,
        'retriever_config': getattr(retriever, 'config', {}), 'commit': git_commit(),
        'summary': summarize(rows), 'cases': rows,
    }


def compare(base: dict, cand: dict) -> dict:
    if base['suite_sha256'] != cand['suite_sha256']:
        raise ValueError('Different suites: re-score both with the same suite')
    b = {r['id']: r for r in base['cases']}
    rows = []
    for r in cand['cases']:
        o = b[r['id']]
        diff = lambda k: None if r[k] is None or o[k] is None else round(r[k] - o[k], 4)
        rows.append({'id': r['id'], 'stage': r['stage'], 'ability': r['ability'],
                     'recall_auto': [o['recall_auto'], r['recall_auto'], diff('recall_auto')],
                     'forbidden_auto': [len(o['forbidden_auto']), len(r['forbidden_auto'])],
                     'stale_as_current': [len(o['stale_as_current']), len(r['stale_as_current'])],
                     'auto_chars': [o['auto_chars'], r['auto_chars']]})
    improved = sum(1 for x in rows if x['recall_auto'][2] is not None and x['recall_auto'][2] > 0)
    worse = sum(1 for x in rows if x['recall_auto'][2] is not None and x['recall_auto'][2] < 0)
    leaks = sum(1 for x in rows if x['forbidden_auto'][1] > x['forbidden_auto'][0]
                or x['stale_as_current'][1] > x['stale_as_current'][0])
    return {'base': base['retriever'], 'candidate': cand['retriever'], 'paired': len(rows),
            'recall_improved': improved, 'recall_worse': worse, 'new_leaks_or_stale': leaks, 'cases': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('score')
    s.add_argument('--retriever', default='current', choices=sorted(RETRIEVERS))
    s.add_argument('--embedder', default='', help='sentence-transformers model for --retriever recall')
    s.add_argument('--keys', help='keys file from write-keys')
    s.add_argument('--llm-url', help='OpenAI-compatible URL for --retriever mind')
    s.add_argument('--thinking', action='store_true', help='let the mind think before answering (--retriever mind)')
    s.add_argument('--out')
    w = sub.add_parser('write-keys')
    w.add_argument('--llm-url', required=True)
    w.add_argument('--model', default='local')
    w.add_argument('--out', required=True)
    c = sub.add_parser('compare')
    c.add_argument('base')
    c.add_argument('candidate')
    args = parser.parse_args(argv)
    if args.command == 'write-keys':
        keys = write_keys(load_suite(), args.llm_url, args.model)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(keys, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'{len(keys["keys"])} keys')
        return
    if args.command == 'score':
        if args.retriever in ('recall', 'mind'):
            keys = json.loads(Path(args.keys).read_text(encoding='utf-8'))['keys'] if args.keys else {}
            embedder = recall.SentenceEmbedder(args.embedder) if args.embedder else None
            if args.retriever == 'mind':
                if not args.llm_url:
                    parser.error('--retriever mind needs --llm-url')
                retriever = MindMethod(embedder, keys, args.llm_url, thinking=args.thinking)
            else:
                retriever = RecallMethod(embedder, keys)
        else:
            retriever = RETRIEVERS[args.retriever]()
        report = run(retriever, load_suite())
        if getattr(retriever, 'calls', None) is not None:
            ms = sorted(c['ms'] for c in retriever.calls)
            report['llm_calls'] = {'n': len(ms), 'median_ms': ms[len(ms) // 2] if ms else None,
                                   'max_ms': ms[-1] if ms else None, 'calls': retriever.calls}
        text = json.dumps(report, ensure_ascii=False, indent=1)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding='utf-8')
        print(json.dumps(report['summary'], ensure_ascii=False, indent=1))
    else:
        load = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
        print(json.dumps(compare(load(args.base), load(args.candidate)), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    sys.exit(main())
