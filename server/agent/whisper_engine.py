"""Offline CPU ASR, shared by the voice adapter and corpus evaluation."""
import threading
import unicodedata

_models = {}
_lock = threading.Lock()


def load_model(path):
    with _lock:
        if path not in _models:
            from faster_whisper import WhisperModel
            _models[path] = WhisperModel(path, device='cpu', compute_type='int8',
                                        cpu_threads=4, num_workers=1, local_files_only=True)
        return _models[path]


def recognize(path, audio, prompt, *, vad_filter=True):
    segments, info = load_model(path).transcribe(audio, language='ja', beam_size=1,
        temperature=0, initial_prompt=prompt or None, vad_filter=vad_filter,
        condition_on_previous_text=False)
    result = ''.join(segment.text for segment in segments).strip()
    # Suppress only a complete vocabulary echo on a subsecond noise segment.
    # Individual names, negation and genuine longer utterances are preserved.
    normalize = lambda text: ''.join(c for c in unicodedata.normalize('NFKC', text)
                                    if not c.isspace() and not unicodedata.category(c).startswith('P'))
    hints = [prompt, *prompt.splitlines()] if prompt else []
    duration = getattr(info, 'duration', None)
    if duration is None:
        duration = len(audio)/16000 if not isinstance(audio, str) else float('inf')
    if duration <= 1 and any(len(normalize(hint)) >= 10 and normalize(result) == normalize(hint)
                                  for hint in hints):
        return ''
    return result
