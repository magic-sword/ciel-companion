"""Offline CPU ASR, shared by the voice adapter and corpus evaluation."""
import threading

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
    segments, _ = load_model(path).transcribe(audio, language='ja', beam_size=1,
        temperature=0, initial_prompt=prompt or None, vad_filter=vad_filter,
        condition_on_previous_text=False)
    return ''.join(segment.text for segment in segments).strip()
