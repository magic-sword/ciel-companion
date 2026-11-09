"""Input settings are independent of LLM tool routing; local defaults to CPU speech."""
import os
from pathlib import Path

def settings(local):
    mode = os.environ.get('CIEL_INPUT') or 'voice'
    backend = os.environ.get('CIEL_STT_BACKEND') or ('vosk' if local else 'openai')
    if mode not in ('text', 'voice') or backend not in ('vosk', 'openai'):
        raise ValueError('Invalid CIEL_INPUT or CIEL_STT_BACKEND')
    if local and mode == 'voice' and backend != 'vosk':
        raise ValueError('Local voice requires Vosk; OpenAI fallback is disabled')
    return mode, backend

def local_stt():
    from vosk_stt import VoskSTT
    path = os.environ.get('CIEL_VOSK_MODEL_PATH', '/models/vosk-model-small-ja-0.22')
    if not Path(path).is_dir():
        raise FileNotFoundError(f'Vosk model is missing: {path}')
    return VoskSTT(path)
