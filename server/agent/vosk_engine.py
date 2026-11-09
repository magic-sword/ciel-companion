"""CPU-only Vosk decoder shared by the live adapter and reproducible measurements."""
import json
from pathlib import Path
import re
import threading

_models = {}
_lock = threading.Lock()
_JA = r"\u3040-\u30ff\u3400-\u9fff"

def text(value):
    # Vosk tokenizes Japanese with spaces. Keep spaces within Latin phrases.
    return re.sub(rf"(?<=[{_JA}])\s+(?=[{_JA}])", "", value or "").strip()

def load_model(path):
    path = str(Path(path).resolve())
    if not Path(path).is_dir():
        raise FileNotFoundError(f"Vosk model directory not found: {path}; provision the model before enabling voice")
    with _lock:
        if path not in _models:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            _models[path] = Model(path)
        return _models[path]

class Decoder:
    def __init__(self, path, sample_rate=16000):
        from vosk import KaldiRecognizer
        self.recognizer = KaldiRecognizer(load_model(path), sample_rate)

    def feed(self, pcm):
        if len(pcm) % 2:
            raise ValueError("Expected signed 16-bit PCM")
        final = bool(self.recognizer.AcceptWaveform(pcm))
        result = json.loads(self.recognizer.Result() if final else self.recognizer.PartialResult())
        return final, text(result.get('text' if final else 'partial'))

    def finish(self):
        result = text(json.loads(self.recognizer.FinalResult()).get('text'))
        self.recognizer.Reset()
        return result
