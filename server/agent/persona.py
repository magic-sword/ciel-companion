# -*- coding: utf-8 -*-
"""会話開始時に、TOML の指定に従って Markdown のプロンプトを読み込む。"""
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import tomllib


DEFAULT_CONFIG = Path(__file__).resolve().parent / 'config' / 'persona.toml'


@dataclass(frozen=True)
class Persona:
    instructions: str
    emotion_instructions: str
    greeting: str
    touch_instructions: str
    group_instructions: str
    speaker_instructions: str

    @property
    def fingerprint(self) -> str:
        """本文をログに残さず、読み込んだプロンプト一式を識別する。"""
        content = json.dumps(
            [self.instructions, self.emotion_instructions, self.greeting, self.touch_instructions,
             self.group_instructions, self.speaker_instructions],
            ensure_ascii=False,
        )
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


def load_persona() -> Persona:
    # 相対パスは起動ディレクトリではなく、このモジュールのディレクトリを基準にする。
    path = Path(os.environ.get('CIEL_PERSONA_CONFIG') or DEFAULT_CONFIG)
    if not path.is_absolute():
        path = DEFAULT_CONFIG.parent.parent / path
    try:
        with path.open('rb') as file:
            config = tomllib.load(file)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f'キャラクター設定を読み込めません: {path}: {exc}') from exc

    values = {}
    for key in ('instructions', 'emotion_instructions', 'greeting', 'touch_instructions', 'group_instructions',
                'speaker_instructions'):
        file_key = f'{key}_file'
        value = config.get(file_key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'キャラクター設定 {path}: {file_key} には空でないファイルパスが必要です')
        prompt_path = Path(value)
        if not prompt_path.is_absolute():
            prompt_path = path.parent / prompt_path
        try:
            content = prompt_path.read_text(encoding='utf-8')
        except (OSError, UnicodeError) as exc:
            raise ValueError(f'プロンプトを読み込めません ({file_key}): {prompt_path}: {exc}') from exc
        if not content.strip():
            raise ValueError(f'プロンプトが空です ({file_key}): {prompt_path}')
        values[key] = content
    return Persona(**values)
