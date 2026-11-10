"""Session-scoped capability discovery. Loading never grants execution permission."""
from collections import OrderedDict
from dataclasses import dataclass
import copy
import hashlib
import json

from livekit.agents import RunContext, ToolError, function_tool
from livekit.agents.llm import utils
import jsonschema


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    summary: str
    tools: frozenset[str]


class CapabilityCatalog:
    MAX_LOADED = 3
    COMMON = frozenset({'register_participant_name', 'get_speaker_status'})
    ALWAYS = frozenset({'current_time', 'stop_game_task', 'game_task_status',
                        'finish_minutes', 'get_minutes_status'})

    def __init__(self, modules):
        definitions = (
            ('1', 'game', 'ゲーム内の体を操作し、目的の作業を依頼する', ('goals',)),
            ('2', 'karaoke', '歌を聴き始める・終える・評価する', ('singing',)),
            ('3', 'memory', '本人確認、同意、本人の思い出の参照・保存・削除', ('people', 'memory')),
            ('4', 'research', 'Webで調査し、出典付きの結果を読む', ('research',)),
            ('5', 'minutes', '会議の議事録を作成し、状態や内容を確認する', ('minutes',)),
            ('6', 'conversation', '現在の会話の履歴を探す', ('conversation',)),
            ('7', 'thoughts', 'シエルの内なる考えを読む・預ける', ('thoughts',)),
            ('8', 'app', '接続しているアプリの表示・動きを操作する', ()),
        )
        groups = {m.__name__.split('.')[-1]: m for m in modules}
        self.services = [Service(i, name, summary, frozenset(
            t.id for group in members for t in groups[group].TOOLS))
            for i, name, summary, members in definitions]
        self.external: dict[str, str] = {}
        self.loaded = OrderedDict()
        self.allowed: set[str] = set()
        self.exposed: set[str] = set()
        self.disabled: set[str] = set()
        self.functions = {}
        self.schemas = {}
        self.issued = {}
        self.instructions = {}
        self.moving = set()
        self.body_calls = OrderedDict()

        @function_tool
        async def load_capabilities(service_ids: list[str]) -> str:
            """必要なサービスの短いIDを1〜3個選び、次の推論で使える道具を読み込む。"""
            return json.dumps(self.load(service_ids), ensure_ascii=False)

        self.loader = load_capabilities

        async def execute(raw_arguments: dict, context: RunContext):
            """Dispatch using the host's current inventory and the caller's trusted context."""
            try:
                jsonschema.validate(raw_arguments, self.executor.info.raw_schema['parameters'])
            except jsonschema.ValidationError as error:
                raise ToolError('実行入口の引数が正しくありません。tool_id・version・argumentsを確認してください。') from error
            name = raw_arguments['tool_id']
            definition = self.definition(name)
            if (definition is None or not self.can_execute(name)
                    or self.issued.get(name) != raw_arguments['version']
                    or definition['version'] != raw_arguments['version']):
                raise ToolError('道具の定義が未取得・変更済み、または現在は許可されていません。必要なら再探索してください。')
            values = raw_arguments['arguments']
            try:
                jsonschema.validate(values, definition['schema']['parameters'])
            except jsonschema.ValidationError as error:
                raise ToolError('道具の引数が取得したスキーマと一致しません。引数を確認してください。') from error
            if name in self.moving:
                key = (id(context.speech_handle), context.speech_handle.num_steps)
                if key in self.body_calls:
                    raise ToolError('一度の返答で実行できる身体操作は一つです。')
                self.body_calls[key] = (context.speech_handle, name)
                while len(self.body_calls) > 64:
                    self.body_calls.popitem(last=False)
            fn = self.functions[name]
            args, kwargs = utils.prepare_function_arguments(fnc=fn, json_arguments=json.dumps(values), call_ctx=context)
            return await fn(*args, **kwargs)

        self.executor = function_tool(execute, raw_schema={
            'name': 'execute_capability',
            'description': '取得済みの道具のID・版・引数で実行する。現在の権限と正規スキーマを再検証する。',
            'parameters': {'type': 'object', 'properties': {
                'tool_id': {'type': 'string'}, 'version': {'type': 'string'},
                'arguments': {'type': 'object'}},
                'required': ['tool_id', 'version', 'arguments'], 'additionalProperties': False}})

    def definition(self, name):
        schema = self.schemas.get(name)
        if schema is None:
            return None
        usage = self.instructions.get(self.service_for(name), '')
        version = hashlib.sha256(json.dumps([schema, usage], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        return {'tool_id': name, 'version': version, 'schema': copy.deepcopy(schema)}

    def can_execute(self, name):
        if name in self.exposed and name not in (self.loader.id, self.executor.id):
            return True
        definition = self.definition(name)
        return bool(name in self.allowed and self.service_for(name) in self.loaded
                    and definition and self.issued.get(name) == definition['version'])

    def target(self, call):
        if call.name == self.executor.id:
            try:
                name = json.loads(call.arguments)['tool_id']
                if isinstance(name, str):
                    return name
            except (ValueError, KeyError, TypeError):
                pass
        return call.name

    def bind_external(self, tools, service: str):
        reserved = {name for s in self.services for name in s.tools} | {self.loader.id, self.executor.id, 'current_time'}
        if any(t.id in reserved for t in tools):
            raise ValueError('external tool collides with a host tool')
        self.external = {name: group for name, group in self.external.items() if group != service}
        self.external.update({t.id: service for t in tools})

    def service_for(self, name: str) -> str | None:
        if name in self.external:
            return self.external[name]
        return next((s.name for s in self.services if name in s.tools), None)

    def available(self):
        return [s for s in self.services if s.name not in self.disabled
                and any(self.service_for(n) == s.name for n in self.allowed)]

    def load(self, ids):
        if not isinstance(ids, list) or not 1 <= len(ids) <= self.MAX_LOADED or any(type(i) is not str for i in ids):
            return {'status': 'invalid_selection'}
        available = {s.id: s for s in self.available()}
        if len(set(ids)) != len(ids) or any(i not in available for i in ids):
            return {'status': 'unavailable', 'available': [s.id for s in available.values()]}
        for i in ids:
            name = available[i].name
            self.loaded.pop(name, None)
            self.loaded[name] = None
        while len(self.loaded) > self.MAX_LOADED:
            removed, _ = self.loaded.popitem(last=False)
            self.issued = {n: v for n, v in self.issued.items() if self.service_for(n) != removed}
        definitions = []
        for i in ids:
            service = available[i]
            tools = []
            for name in sorted(self.allowed):
                if self.service_for(name) == service.name:
                    definition = self.definition(name)
                    if definition is not None:
                        self.issued[name] = definition['version']
                        tools.append(definition)
            definitions.append({'id': i, 'name': service.name, 'tools': tools,
                                'instructions': self.instructions.get(service.name, '')})
        return {'status': 'loaded', 'services': list(self.loaded), 'definitions': definitions, 'executed': False}

    def select(self, eligible):
        """Called after origin/ownership filters, on every inference including tool continuations."""
        controls = {self.loader.id, self.executor.id}
        self.functions = {t.id: t for t in eligible if t.id not in controls}
        self.allowed = {t.id for t in eligible if t.id not in controls
                        and self.service_for(t.id) not in self.disabled}
        for fn in eligible:
            if fn.id in self.allowed and getattr(fn, 'info', None) is not None:
                schema = copy.deepcopy(getattr(fn.info, 'raw_schema', None) or utils.build_legacy_openai_schema(fn)['function'])
                schema['parameters']['additionalProperties'] = False
                self.schemas[fn.id] = schema
        visible = [t for t in eligible if t.id in controls or
                   (t.id in self.allowed and t.id in self.ALWAYS | self.COMMON)]
        self.exposed = {t.id for t in visible}
        return visible

    def summary(self):
        return json.dumps({'services': [{'id': s.id, 'name': s.name, 'summary': s.summary}
                                       for s in self.services if s.name not in self.disabled
                                       and (s.tools or s.name in self.external.values())]},
                          ensure_ascii=False, separators=(',', ':'))
