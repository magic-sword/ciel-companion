"""Session-scoped capability discovery. Loading never grants execution permission."""
from collections import OrderedDict
from dataclasses import dataclass
import json

from livekit.agents import function_tool


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    summary: str
    tools: frozenset[str]


class CapabilityCatalog:
    MAX_LOADED = 3
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

        @function_tool
        async def load_capabilities(service_ids: list[str]) -> str:
            """必要なサービスの短いIDを1〜3個選び、次の推論で使える道具を読み込む。"""
            return json.dumps(self.load(service_ids), ensure_ascii=False)

        self.loader = load_capabilities

    def bind_external(self, tools, service: str):
        reserved = {name for s in self.services for name in s.tools} | {self.loader.id, 'current_time'}
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
            self.loaded.popitem(last=False)
        return {'status': 'loaded', 'services': list(self.loaded),
                'next': '選択したサービスの道具は次の推論に公開されます。まだ実行していません。'}

    def select(self, eligible):
        """Called after origin/ownership filters, on every inference including tool continuations."""
        self.allowed = {t.id for t in eligible if t.id != self.loader.id
                        and self.service_for(t.id) not in self.disabled}
        visible = [t for t in eligible if t.id == self.loader.id or
                   (t.id in self.allowed and (t.id in self.ALWAYS or self.service_for(t.id) in self.loaded))]
        self.exposed = {t.id for t in visible}
        return visible

    def summary(self):
        return json.dumps({'services': [{'id': s.id, 'name': s.name, 'summary': s.summary}
                                       for s in self.available()],
                           'loaded': [s for s in self.loaded if any(a.name == s for a in self.available())]},
                          ensure_ascii=False, separators=(',', ':'))
