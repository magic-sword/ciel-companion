"""Input settings are independent of LLM tool routing; local defaults to CPU speech."""
import os
from pathlib import Path

def settings(local):
    mode = os.environ.get('CIEL_INPUT') or 'voice'
    backend = os.environ.get('CIEL_STT_BACKEND') or ('vosk' if local else 'openai')
    if mode not in ('text', 'voice') or backend not in ('vosk', 'whisper', 'openai'):
        raise ValueError('Invalid CIEL_INPUT or CIEL_STT_BACKEND')
    if local and mode == 'voice' and backend not in ('vosk', 'whisper'):
        raise ValueError('Local voice requires local STT; OpenAI fallback is disabled')
    return mode, backend

def local_stt(*, vad=None, names=()):
    if os.environ.get('CIEL_STT_BACKEND') == 'whisper':
        from livekit.agents import stt
        from whisper_stt import WhisperSTT
        from persona import load_persona
        path = os.environ.get('CIEL_WHISPER_MODEL_PATH', '/models-whisper/small')
        if not Path(path).is_dir():
            raise FileNotFoundError(f'Whisper model is missing: {path}')
        if vad is None:
            raise ValueError('Whisper streaming requires VAD')
        prompt = load_persona().stt_vocabulary
        if names:
            prompt += '\n' + '、'.join(dict.fromkeys(names))[:400]
        return stt.StreamAdapter(stt=WhisperSTT(path, prompt), vad=vad)
    from vosk_stt import VoskSTT
    path = os.environ.get('CIEL_VOSK_MODEL_PATH', '/models/vosk-model-small-ja-0.22')
    if not Path(path).is_dir():
        raise FileNotFoundError(f'Vosk model is missing: {path}')
    return VoskSTT(path)


def prepare():
    if os.environ.get('CIEL_STT_BACKEND') == 'whisper':
        from whisper_engine import load_model
        load_model(os.environ.get('CIEL_WHISPER_MODEL_PATH', '/models-whisper/small'))
    else:
        from vosk_engine import load_model
        load_model(os.environ.get('CIEL_VOSK_MODEL_PATH', '/models/vosk-model-small-ja-0.22'))
