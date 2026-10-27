# -*- coding: utf-8 -*-
"""歌声から「聴いた印象の手がかり」を取り出す（server.py から使う。numpy だけで動き、モデルの結果は引数で受け取る）。

方針（docs/singing-evaluation-research-ja.md の 7 章）：音程を原曲に合わせることは目標にしない。
- 心に響いたか：Audiobox Aesthetics の CE（Content Enjoyment）を区間ごとに見て、いちばん響いた所を探す
- 感動の瞬間の候補：曲の展開の変化（MERT の特徴の変わり目）と、盛り上がり（920〜4400 Hz の音量の増加。鳥肌の研究）
- 個性：曲を通して繰り返すくせ（しゃくり・フォール・ビブラート）はほめる側に回す
- 崩れ：ばらばらに揺れた伸ばす音と、外れて聞こえたかもしれない音だけを、提案の候補にする
ときめき度（tokimeki）は、正しさの点数ではなく、シエルの主観の点数。言葉にするのは会話サーバー（server/agent/singing.py）。
"""
from dataclasses import dataclass

import numpy as np

SR = 16000
HOP = 0.01             # 音の高さの刻み（秒）
FRAME = 0.05           # 音量の刻み（秒）
WINDOW, WINDOW_HOP = 10.0, 5.0   # 心に響いたかを見る区間（Audiobox Aesthetics は 10 秒ずつ見る）
PRESENCE_BAND = (920.0, 4400.0)  # 鳥肌が立った所で音量が上がっていた帯域（Nagel ら 2008）
BUILD_DB = 3.0         # 前の区間より、これだけ帯域の音量が上がったら「盛り上がり」
NOTE_JUMP = 70.0       # これより音の高さが離れたら、次の音（セント）
MIN_NOTE = 0.15        # これより短い音は数えない（秒）
LONG_NOTE = 0.8        # 伸ばす音（秒）
SCOOP_CENTS = 80.0     # 音の入りで、これより下から上がってきたら「しゃくり」
FALL_CENTS = 100.0     # 音の終わりで、これより下がったら「フォール」
HABIT_RATIO = 0.3      # 音のうちこれ以上の割合で出るくせは、その人の個性として扱う
WOBBLE_CENTS = 30.0    # ビブラートでないのに、伸ばす音がこれより揺れたら「揺れ」
OFF_CENTS = 40.0       # その人の音の基準から、これよりずれた音は「外れて聞こえたかも」
PERIODICITY = 0.5      # 音の高さを信じる、声の周期のはっきりさ（torchcrepe）
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# 調の推定（Krumhansl-Kessler の調性のプロファイル）
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def frame_db(audio: np.ndarray, sr: int = SR, frame: float = FRAME) -> np.ndarray:
    n = int(sr * frame)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if len(frames) == 0:
        return np.zeros(0)
    return 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)


def voiced(db: np.ndarray) -> np.ndarray:
    """声が出ている刻み（いちばん大きい所から 35 dB 以内で、-50 dB より大きい）"""
    if len(db) == 0:
        return np.zeros(0, bool)
    return db > max(-50.0, float(np.percentile(db, 95)) - 35.0)


def trim(audio: np.ndarray, sr: int = SR, pad: float = 0.3) -> tuple[np.ndarray, float]:
    """前後の無音を落とす。落とした後の音と、頭で落とした秒数"""
    on = np.flatnonzero(voiced(frame_db(audio, sr)))
    if len(on) == 0:
        return audio[:0], 0.0
    start = max(0.0, on[0] * FRAME - pad)
    end = min(len(audio) / sr, (on[-1] + 1) * FRAME + pad)
    return audio[int(start * sr):int(end * sr)], start


def band_db(audio: np.ndarray, sr: int = SR, band: tuple[float, float] = PRESENCE_BAND,
            frame: float = FRAME) -> np.ndarray:
    n = int(sr * frame)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if len(frames) == 0:
        return np.zeros(0)
    spec = np.abs(np.fft.rfft(frames * np.hanning(n), axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1 / sr)
    sel = (freqs >= band[0]) & (freqs <= band[1])
    return 10 * np.log10(spec[:, sel].sum(1) / n + 1e-12)


def windows(duration: float) -> list[tuple[float, float]]:
    """心に響いたかを見る区間。短い歌は 1 区間"""
    if duration <= WINDOW:
        return [(0.0, duration)]
    starts = np.arange(0.0, duration - WINDOW / 2, WINDOW_HOP)
    return [(float(s), float(min(s + WINDOW, duration))) for s in starts]


def note_name(cents: float) -> str:
    midi = int(round(cents / 100))
    return f'{NOTE_NAMES[midi % 12]}{midi // 12 - 1}'


@dataclass
class Note:
    start: float        # 秒
    end: float
    pitch: float        # 音の芯（セント。MIDI × 100）
    scoop: bool = False
    fall: bool = False
    vibrato: tuple[float, float] | None = None   # (速さ Hz, 深さ セント)
    wobble: bool = False

    @property
    def length(self) -> float:
        return self.end - self.start


def to_cents(f0: np.ndarray) -> np.ndarray:
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(f0 > 0, 1200 * np.log2(np.maximum(f0, 1e-9) / 440.0) + 6900, np.nan)


def split_notes(cents: np.ndarray, hop: float = HOP) -> list[tuple[int, int]]:
    """音の高さの列を、音ごとの [始め, 終わり) の刻みに分ける。声が切れるか、高さが NOTE_JUMP 離れて 3 刻み続いたら次の音"""
    notes, start, run, ref = [], None, 0, None
    for i, c in enumerate(cents):
        if np.isnan(c):
            if start is not None:
                notes.append((start, i - run))
            start, run, ref = None, 0, None
            continue
        if start is None:
            start, run, ref = i, 0, c
            continue
        ref = float(np.median(cents[max(start, i - 10):i]))
        if abs(c - ref) > NOTE_JUMP:
            run += 1
            if run >= 3:
                notes.append((start, i - run + 1))
                start, run = i - run + 1, 0
        else:
            run = 0
    if start is not None:
        notes.append((start, len(cents)))
    return [(a, b) for a, b in notes if (b - a) * hop >= MIN_NOTE]


def vibrato(residual: np.ndarray, hop: float = HOP) -> tuple[float, float] | None:
    """伸ばす音の揺れが、4〜8 Hz のはっきりした周期ならビブラート（速さ Hz, 深さ セント）"""
    if len(residual) < int(0.5 / hop):
        return None
    spec = np.abs(np.fft.rfft(residual * np.hanning(len(residual)))) ** 2
    freqs = np.fft.rfftfreq(len(residual), hop)
    band = (freqs >= 4) & (freqs <= 8)
    wide = (freqs >= 1) & (freqs <= 12)
    if not band.any() or spec[wide].sum() == 0:
        return None
    depth = float(np.percentile(residual, 90) - np.percentile(residual, 10)) / 2
    if spec[band].sum() / spec[wide].sum() < 0.5 or depth < 15:
        return None
    return float(freqs[band][np.argmax(spec[band])]), depth


def describe_note(cents: np.ndarray, a: int, b: int, hop: float = HOP) -> Note:
    seg = cents[a:b]
    n = len(seg)
    core = seg[n // 4: n - n // 4] if n >= 8 else seg
    pitch = float(np.median(core))
    head = seg[: max(1, int(0.12 / hop))]
    tail = seg[-max(1, int(0.15 / hop)):]
    note = Note(a * hop, b * hop, pitch,
                scoop=bool(pitch - head[0] >= SCOOP_CENTS and head[-1] > head[0]),
                fall=bool(pitch - tail[-1] >= FALL_CENTS and n * hop >= 0.3))
    if note.length >= LONG_NOTE:
        edge = int(0.15 / hop)
        body = seg[edge: n - edge]
        t = np.arange(len(body))
        residual = body - np.polyval(np.polyfit(t, body, 2), t)
        note.vibrato = vibrato(residual, hop)
        note.wobble = note.vibrato is None and float(np.std(residual)) > WOBBLE_CENTS
    return note


def estimate_key(notes: list[Note]) -> tuple[str, float, list[int]]:
    """その人の音の基準（ずれ セント）と、調の名前、調の音（0〜11）。音程を原曲に合わせるためではなく、
    その人がいつも少し低め・高めでも、それを基準にして「外れて聞こえたかも」を見るため"""
    weights = np.array([n.length for n in notes])
    frac = np.array([n.pitch % 100 for n in notes]) / 100 * 2 * np.pi
    tuning = float(np.angle((weights * np.exp(1j * frac)).sum()) / (2 * np.pi) * 100)
    hist = np.zeros(12)
    for n, w in zip(notes, weights):
        hist[int(round((n.pitch - tuning) / 100)) % 12] += w
    best = (-2.0, 0, 'major')
    for tonic in range(12):
        for name, profile in (('major', MAJOR), ('minor', MINOR)):
            r = float(np.corrcoef(hist, np.roll(profile, tonic))[0, 1]) if hist.std() > 0 else 0.0
            if r > best[0]:
                best = (r, tonic, name)
    _, tonic, mode = best
    steps = [0, 2, 4, 5, 7, 9, 11] if mode == 'major' else [0, 2, 3, 5, 7, 8, 10]
    label = f'{NOTE_NAMES[tonic]} {"メジャー" if mode == "major" else "マイナー"}'
    return label, tuning, [(tonic + s) % 12 for s in steps]


def off_notes(notes: list[Note], tuning: float, scale: list[int]) -> list[Note]:
    """外れて聞こえたかもしれない音：その人の基準から OFF_CENTS 以上ずれた、0.4 秒以上の音。
    しゃくり・ビブラートの音と、調の外の音（わざと使った半音かもしれない）は除く"""
    out = []
    for n in notes:
        if n.length < 0.4 or n.vibrato is not None:
            continue
        rel = n.pitch - tuning
        semitone = round(rel / 100)
        if semitone % 12 in scale and abs(rel - semitone * 100) >= OFF_CENTS:
            out.append(n)
    return out


def attack_ms(db: np.ndarray, frame: float = FRAME) -> float | None:
    """声の入り：声が出始めてから、その声の大きさの -3 dB に届くまでの時間（中央値、ミリ秒）"""
    on = voiced(db)
    times = []
    i = 0
    while i < len(on):
        if on[i] and (i == 0 or not on[i - 1]):
            seg = db[i: i + int(0.3 / frame)]
            peak = seg.max()
            times.append(int(np.argmax(seg >= peak - 3)) * frame * 1000)
        i += 1
    return float(np.median(times)) if times else None


def spectral(audio: np.ndarray, sr: int = SR, frame: float = FRAME) -> tuple[float | None, float | None]:
    """声の明るさ（スペクトルの重心 Hz）と、息の混ざり（5 kHz より上の割合）。声が出ている刻みだけ"""
    n = int(sr * frame)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if len(frames) == 0:
        return None, None
    frames = frames[voiced(frame_db(audio, sr, frame))]
    if len(frames) == 0:
        return None, None
    spec = np.abs(np.fft.rfft(frames * np.hanning(n), axis=1)) ** 2
    freqs = np.fft.rfftfreq(n, 1 / sr)
    total = spec.sum(1) + 1e-12
    centroid = float(np.median((spec * freqs).sum(1) / total))
    breath = float(np.median(spec[:, freqs >= 5000].sum(1) / total))
    return centroid, breath


def moments(aes: list[dict], spans: list[tuple[float, float]], builds: list[float], changes: list[float],
            limit: int = 3) -> list[dict]:
    """ぐっときた瞬間の候補。いちばん響いた区間に、盛り上がり・展開の変化が重なった所を先に並べる"""
    if not aes:
        return []
    ce = np.array([a['CE'] for a in aes])
    found = []
    for i in np.argsort(-ce):
        a, b = spans[i]
        why = ['響いた'] if ce[i] >= np.median(ce) else []
        why += ['盛り上がり'] * any(a <= t < b for t in builds)
        why += ['展開の変化'] * any(a <= t < b for t in changes)
        if why:
            found.append({'start': round(a, 1), 'end': round(b, 1), 'ce': round(float(ce[i]), 2), 'why': why})
    found.sort(key=lambda m: (-len(m['why']), -m['ce']))
    picked = []
    for m in found:
        if all(m['end'] <= p['start'] or m['start'] >= p['end'] for p in picked):
            picked.append(m)
        if len(picked) >= limit:
            break
    return sorted(picked, key=lambda m: m['start'])


def builds(audio: np.ndarray, spans: list[tuple[float, float]], sr: int = SR) -> list[float]:
    """盛り上がり：前の 2 区間より、920〜4400 Hz の声の音量が BUILD_DB 以上上がった区間の始め"""
    band = band_db(audio, sr)
    on = voiced(frame_db(audio, sr))
    levels = []
    for a, b in spans:
        sel = on[int(a / FRAME):int(b / FRAME)]
        seg = band[int(a / FRAME):int(b / FRAME)][sel] if sel.any() else np.zeros(0)
        levels.append(float(np.mean(seg)) if len(seg) else None)
    out = []
    for i in range(1, len(levels)):
        prev = [v for v in levels[max(0, i - 2):i] if v is not None]
        if levels[i] is not None and prev and levels[i] - np.mean(prev) >= BUILD_DB:
            out.append(spans[i][0])
    return out


def changes(embeddings: np.ndarray, spans: list[tuple[float, float]], limit: int = 3) -> list[float]:
    """展開の変化：MERT の区間ごとの特徴が、前の区間から大きく変わった所（平均より 1 標準偏差以上）"""
    if len(embeddings) < 3:
        return []
    e = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9)
    dist = 1 - (e[1:] * e[:-1]).sum(1)
    cut = dist.mean() + dist.std()
    idx = [i for i in np.argsort(-dist)[:limit] if dist[i] >= cut and dist[i] > 0]
    return sorted(spans[i + 1][0] for i in idx)


def analyze(audio: np.ndarray, f0: np.ndarray, periodicity: np.ndarray, aes: list[dict],
            embeddings: np.ndarray, spans: list[tuple[float, float]], sr: int = SR) -> dict:
    """手がかりをまとめる。audio は trim 済み、f0・periodicity は HOP 刻み、aes と embeddings は spans の区間ごと"""
    duration = len(audio) / sr
    db = frame_db(audio, sr)
    on = voiced(db)
    cents = to_cents(np.where(periodicity >= PERIODICITY, f0, 0.0))
    notes = [describe_note(cents, a, b) for a, b in split_notes(cents)]
    build_times = builds(audio, spans, sr)
    change_times = changes(embeddings, spans) if len(embeddings) else []
    centroid, breath = spectral(audio, sr)
    attack = attack_ms(db)
    result = {
        'duration': round(duration, 1),
        'sung_seconds': round(float(on.sum()) * FRAME, 1),
        'aesthetics': None,
        'moments': moments(aes, spans, build_times, change_times),
        'builds': [round(t, 1) for t in build_times],
        'changes': [round(t, 1) for t in change_times],
        'dynamics_db': round(float(np.percentile(db[on], 95) - np.percentile(db[on], 10)), 1) if on.any() else None,
        'voice': {
            'attack': None if attack is None else 'soft' if attack >= 120 else 'hard' if attack <= 50 else 'medium',
            'attack_ms': None if attack is None else round(attack),
            'brightness_hz': None if centroid is None else round(centroid),
            'breath_ratio': None if breath is None else round(breath, 3),
        },
        'pitch': None,
    }
    if aes:
        ce = [a['CE'] for a in aes]
        result['aesthetics'] = {
            'ce_mean': round(float(np.mean(ce)), 2), 'ce_max': round(float(np.max(ce)), 2),
            'ce_min': round(float(np.min(ce)), 2), 'pq_mean': round(float(np.mean([a['PQ'] for a in aes])), 2),
            'windows': [{'start': round(a, 1), 'end': round(b, 1), 'ce': round(x['CE'], 2)}
                        for (a, b), x in zip(spans, aes)],
        }
    if len(notes) >= 3:
        key, tuning, scale = estimate_key(notes)
        long_notes = [n for n in notes if n.length >= LONG_NOTE]
        vib = [n.vibrato for n in notes if n.vibrato is not None]
        pitches = np.array([n.pitch for n in notes])
        result['pitch'] = {
            'notes': len(notes),
            'range': [note_name(float(np.percentile(pitches, 5))), note_name(float(np.percentile(pitches, 95)))],
            'key': key,
            'tuning_cents': round(tuning),
            'long_notes': len(long_notes),
            'vibrato': {'count': len(vib), 'rate_hz': round(float(np.mean([v[0] for v in vib])), 1),
                        'depth_cents': round(float(np.mean([v[1] for v in vib])))} if vib else {'count': 0},
            'scoop_ratio': round(sum(n.scoop for n in notes) / len(notes), 2),
            'fall_ratio': round(sum(n.fall for n in notes) / len(notes), 2),
            'habits': [name for name, ratio in (('しゃくり', sum(n.scoop for n in notes) / len(notes)),
                                                ('フォール', sum(n.fall for n in notes) / len(notes)),
                                                ('ビブラート', len(vib) / max(1, len(long_notes))))
                       if ratio >= HABIT_RATIO],
            'wobbles': [round(n.start, 1) for n in long_notes if n.wobble][:5],
            'off': [round(n.start, 1) for n in off_notes(notes, tuning, scale)][:5],
            'off_ratio': round(len(off_notes(notes, tuning, scale)) / len(notes), 2),
        }
    result['tokimeki'] = tokimeki(result)
    return result


# ---- ときめき度（シエルの主観の点数。仮の目盛り：本物の歌を何曲か聴いてから合わせ直す） ----
TOKIMEKI_BASE = 40        # 聴かせてくれたことへの点。正しさの減点はしない
TOKIMEKI_PARTS = (('響き', 25), ('ぐっときた瞬間', 15), ('表現', 12), ('伸び', 8))
CE_LOW, CE_HIGH = 3.0, 7.0   # 心に響いた度（CE）をこの幅で 0〜1 にする。スマホのアカペラは 4〜5 くらい（合成の歌声で 4.2〜4.9）


def ce_level(ce: float) -> float:
    return float(np.clip((ce - CE_LOW) / (CE_HIGH - CE_LOW), 0.0, 1.0))


def tokimeki(result: dict) -> dict:
    """ときめき度（0〜100）と内わけ。いちばん響いた所・ぐっときた瞬間・表現の幅・伸ばす音の安定から足していく"""
    aes, pitch = result.get('aesthetics'), result.get('pitch')
    hibiki = ce_level(aes['ce_max']) if aes else 0.0
    moment = min(1.0, sum(len(m['why']) for m in result.get('moments', [])) / 6)
    dyn = result.get('dynamics_db') or 0.0
    expression = (float(np.clip((dyn - 6) / 14, 0, 1)) * 0.5
                  + 0.25 * bool(result.get('builds') or result.get('changes'))
                  + 0.125 * min(2, len(pitch['habits']) if pitch else 0))
    if pitch and pitch['long_notes']:
        nobi = 1 - len(pitch['wobbles']) / pitch['long_notes']
    else:
        nobi = 0.5
    values = (hibiki, moment, expression, nobi)
    parts = [{'name': name, 'value': round(v * top), 'max': top} for (name, top), v in zip(TOKIMEKI_PARTS, values)]
    return {'score': TOKIMEKI_BASE + sum(p['value'] for p in parts), 'parts': parts}


def live(audio: np.ndarray, f0: np.ndarray, periodicity: np.ndarray, sr: int = SR) -> dict:
    """歌っている途中の 10 秒の手がかり（心に響いた度・帯域の音量・MERT の特徴は server.py が足す）"""
    db = frame_db(audio, sr)
    on = voiced(db) & (db > -50)
    band = band_db(audio, sr)
    cents = to_cents(np.where(periodicity >= PERIODICITY, f0, 0.0))
    notes = [describe_note(cents, a, b) for a, b in split_notes(cents)]
    return {
        'voiced': round(float(on.mean()), 2) if len(on) else 0.0,
        'band_db': round(float(band[on].mean()), 1) if on.any() else None,
        'notes': len(notes),
        'scoops': sum(n.scoop for n in notes),
        'vibratos': sum(n.vibrato is not None for n in notes),
        'wobbles': sum(n.wobble for n in notes),
    }
