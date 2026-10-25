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
    greeting_owner: str
    enroll_done: str
    touch_instructions: str
    talk_quiet_instructions: str
    talk_quiet_turn_instructions: str
    talk_chatty_instructions: str
    talk_chatty_nudge: str
    inner_thoughts_instructions: str
    talk_correction_nudge: str
    talk_inner_state_instructions: str
    inner_thoughts_voice_instructions: str
    presence_solo_instructions: str
    presence_close_instructions: str
    presence_public_instructions: str
    speaker_instructions: str
    notes_instructions: str
    relationship_instructions: str
    minutes_instructions: str
    minutes_live_instructions: str
    minutes_voice_instructions: str
    conversation_instructions: str
    research_instructions: str
    research_voice_instructions: str

    @property
    def fingerprint(self) -> str:
        """本文をログに残さず、読み込んだプロンプト一式を識別する。"""
        content = json.dumps(
            [self.instructions, self.emotion_instructions, self.greeting, self.greeting_owner, self.enroll_done, self.touch_instructions,
             self.talk_quiet_instructions, self.talk_quiet_turn_instructions, self.talk_chatty_instructions,
             self.talk_chatty_nudge, self.inner_thoughts_instructions, self.talk_correction_nudge,
             self.talk_inner_state_instructions, self.inner_thoughts_voice_instructions,
             self.presence_solo_instructions, self.presence_close_instructions,
             self.presence_public_instructions, self.speaker_instructions, self.notes_instructions,
             self.relationship_instructions, self.minutes_instructions, self.minutes_live_instructions,
             self.minutes_voice_instructions,
             self.conversation_instructions, self.research_instructions, self.research_voice_instructions],
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
    for key in ('instructions', 'emotion_instructions', 'greeting', 'greeting_owner', 'enroll_done', 'touch_instructions',
                'talk_quiet_instructions', 'talk_quiet_turn_instructions', 'talk_chatty_instructions',
                'talk_chatty_nudge', 'inner_thoughts_instructions', 'talk_correction_nudge',
                'talk_inner_state_instructions', 'inner_thoughts_voice_instructions',
                'presence_solo_instructions', 'presence_close_instructions',
                'presence_public_instructions', 'speaker_instructions', 'notes_instructions', 'relationship_instructions',
                'minutes_instructions', 'minutes_live_instructions', 'minutes_voice_instructions',
                'conversation_instructions',
                'research_instructions', 'research_voice_instructions'):
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
