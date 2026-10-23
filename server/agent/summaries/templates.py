"""テンプレート：config/summaries/<名前>.toml（見出しと種類）と、guide_file の Markdown（書き方の指示。モデルへそのまま渡す）。
会話の始めに読み込み、その会話の中では変えない。足すときは TOML と Markdown を 1 組置くだけでよい。"""
import tomllib
from dataclasses import dataclass
from pathlib import Path

from summaries.kinds import KINDS

DEFAULT_DIR = Path(__file__).resolve().parent.parent / 'config' / 'summaries'
DEFAULT = 'meeting'


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    kind: str


@dataclass(frozen=True)
class Template:
    name: str
    label: str          # 画面とシエルの一言で使う呼び名（「会議の議事録」など）
    description: str
    guide: str          # 書き方の指示（Markdown）
    sections: tuple[Section, ...]

    def section(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def for_model(self) -> dict:
        return {'name': self.name, 'label': self.label, 'guide': self.guide,
                'sections': [{'id': s.id, 'label': s.label, 'kind': s.kind} for s in self.sections]}


def load(directory: Path = DEFAULT_DIR) -> dict[str, Template]:
    templates = {}
    for path in sorted(directory.glob('*.toml')):
        try:
            config = tomllib.loads(path.read_text(encoding='utf-8'))
            guide = (path.parent / config['guide_file']).read_text(encoding='utf-8').strip()
            sections = tuple(Section(s['id'], s['label'], s['kind']) for s in config['sections'])
            label, description = config['label'], config.get('description', '')
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f'まとめのテンプレートを読み込めません: {path}: {exc}') from exc
        ids = [s.id for s in sections]
        if not sections or len(set(ids)) != len(ids) or any(s.kind not in KINDS or not s.id.isidentifier() for s in sections):
            raise ValueError(f'まとめのテンプレートの見出しが正しくありません: {path}')
        if not guide:
            raise ValueError(f'まとめのテンプレートの書き方が空です: {path}')
        templates[path.stem] = Template(path.stem, label, description, guide, sections)
    if DEFAULT not in templates:
        raise ValueError(f'まとめのテンプレート {DEFAULT} がありません: {directory}')
    return templates
