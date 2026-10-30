# -*- coding: utf-8 -*-
"""どこでどのモデルを使うかの一覧と、呼ぶたびの使用量・料金の記録。

役目ごとのモデルは、それぞれの環境変数で変えられる（今までと同じ名前）。この一覧が、どこでどのモデルが動くかの正。
呼んだ側は、返ってきた使用量を record() に渡す。ログには役目・モデル・トークン数・料金の目安だけを出す（会話の中身は出さない）。
デバッグ用の会話ログ（debug_log）にも 'model_usage' として残し、bench_compare.py が会話ごとの料金を足し合わせる。
単価は docs/paid-checks-ja.md の 2026-10 の表（100 万トークンあたり、米ドル）。知らないモデルは料金を 0 にして、ログに残す。
"""
import logging
import os

import debug_log

log = logging.getLogger('ciel-agent.models')

# 役目 → (環境変数, 既定のモデル)
ROLES = {
    'talk': ('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini'),     # 返事の文を作る（Realtime。使用量は usage.py）
    'mind': ('CIEL_MIND_MODEL', 'gpt-5.4-mini'),                  # 返事の文を作る（CIEL_MODEL=pipeline の心。mind.py。使用量は usage.py）
    'brief': ('CIEL_BRIEF_MODEL', 'gpt-5.4-mini'),                # 心が「今のまとめ」を書く（mind.py）
    'stt': ('CIEL_STT_MODEL', 'gpt-realtime-whisper'),            # 文字起こし（CIEL_MODEL=pipeline。話している途中から文字が出る）
    'thought': ('CIEL_THOUGHT_MODEL', 'gpt-5.4-mini'),            # 内なる考え（initiative.py）
    'minutes_live': ('CIEL_MINUTES_LIVE_MODEL', 'gpt-5.4-mini'),  # 議事録のライブ（minutes.py）
    'minutes': ('CIEL_MINUTES_MODEL', 'gpt-5.4'),                 # 議事録の清書（minutes.py）
    'notes': ('CIEL_NOTES_MODEL', 'gpt-5.4-mini'),                # メモ（notes.py）
    'relationship': ('CIEL_NOTES_MODEL', 'gpt-5.4-mini'),         # 関係（relationship.py。メモと同じモデル）
    'research': ('CIEL_RESEARCH_MODEL', 'gpt-5.4-mini'),          # 調べもの（web_research.py）
}

# モデル → (入力, キャッシュ, 出力) の単価。Realtime は文字と音声で入力の単価が違う（AUDIO_INPUT）
PRICES = {
    'gpt-realtime-2.1-mini': (0.60, 0.06, 2.40),
    'gpt-5.4': (2.50, 0.25, 15.00),
    'gpt-5.4-mini': (0.75, 0.075, 4.50),
    'gpt-4o-mini-transcribe': (1.25, 1.25, 5.00),
}
AUDIO_INPUT = {'gpt-realtime-2.1-mini': (10.00, 0.30)}   # 音声の入力・そのキャッシュ
# 音声の長さで払う文字起こし（1 分あたり、米ドル。OpenAI のモデルの説明のページ、2026-10）
PER_MINUTE = {'gpt-realtime-whisper': 0.017, 'gpt-live-transcribe': 0.017}


def model(role: str) -> str:
    env, default = ROLES[role]
    return os.environ.get(env, default)


def cost(model_name: str, input_tokens: int, cached: int, output_tokens: int,
         audio_input: int = 0, audio_cached: int = 0) -> float:
    """料金の目安（米ドル）。audio_input・audio_cached は input_tokens・cached の内数"""
    price = PRICES.get(model_name)
    if price is None:
        return 0.0
    text_in, text_cached = input_tokens - audio_input, cached - audio_cached
    audio = AUDIO_INPUT.get(model_name, (price[0], price[1]))
    usd = ((text_in - text_cached) * price[0] + text_cached * price[1]
           + (audio_input - audio_cached) * audio[0] + audio_cached * audio[1] + output_tokens * price[2])
    return usd / 1_000_000


def cost_per_minute(model_name: str, minutes: float) -> float:
    return PER_MINUTE.get(model_name, 0.0) * minutes


def record(role: str, model_name: str, usage) -> None:
    """Chat Completions・Responses の使用量を記録する（usage が無ければ何もしない）"""
    if usage is None:
        return
    try:
        if hasattr(usage, 'prompt_tokens'):   # Chat Completions
            inp, out = usage.prompt_tokens or 0, usage.completion_tokens or 0
            cached = getattr(getattr(usage, 'prompt_tokens_details', None), 'cached_tokens', 0) or 0
            reasoning = getattr(getattr(usage, 'completion_tokens_details', None), 'reasoning_tokens', 0) or 0
        else:                                 # Responses
            inp, out = usage.input_tokens or 0, usage.output_tokens or 0
            cached = getattr(getattr(usage, 'input_tokens_details', None), 'cached_tokens', 0) or 0
            reasoning = getattr(getattr(usage, 'output_tokens_details', None), 'reasoning_tokens', 0) or 0
    except (AttributeError, TypeError):
        return
    usd = cost(model_name, inp, cached, out)
    log.info('使用量 %s %s 入力 %s（キャッシュ %s） 出力 %s（考える %s） 約 %.4f ドル',
             role, model_name, f'{inp:,}', f'{cached:,}', f'{out:,}', f'{reasoning:,}', usd)
    debug_log.record('model_usage', role=role, model=model_name, input_tokens=inp, cached_tokens=cached,
                     output_tokens=out, reasoning_tokens=reasoning, usd=round(usd, 6))
