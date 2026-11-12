# -*- coding: utf-8 -*-
"""どこでどのモデルを使うかの一覧と、呼ぶたびの使用量・料金の記録。

役目ごとのモデルは、それぞれの環境変数で変えられる（今までと同じ名前）。この一覧が、どこでどのモデルが動くかの正。
呼んだ側は、返ってきた使用量を record() に渡す。ログには役目・モデル・トークン数・料金の目安だけを出す（会話の中身は出さない）。
デバッグ用の会話ログ（debug_log）にも 'model_usage' として残し、bench_compare.py が会話ごとの料金を足し合わせる。
単価は docs/testing/paid-checks-ja.md の 2026-10 の表（100 万トークンあたり、米ドル）。知らないモデルは料金を 0 にして、ログに残す。
"""
import logging
import os
from types import SimpleNamespace
import inference_activity

import debug_log

log = logging.getLogger('ciel-agent.models')

# local は試験用。通常の役目別切り替えとは別に、文字の推論をまとめて手元へ送る。
BACKEND = os.environ.get('CIEL_LLM_BACKEND', 'openai').strip().lower()
if BACKEND not in ('openai', 'local'):
    raise ValueError('CIEL_LLM_BACKEND must be openai or local')
LOCAL_TEST = BACKEND == 'local'

# 役目 → (環境変数, 既定のモデル)
ROLES = {
    'talk': ('CIEL_REALTIME_MODEL', 'gpt-realtime-2.1-mini'),     # 返事の文を作る（Realtime。使用量は usage.py）
    'mind': ('CIEL_MIND_MODEL', 'gpt-5.4-mini'),                  # 返事の文を作る（CIEL_MODEL=pipeline の心。mind.py。使用量は usage.py）
    'listener': ('CIEL_LISTENER_MODEL', 'gpt-5.4-mini'),          # 聞く係が、話の途中の頼みを確かめる（listener.py）
    'brief': ('CIEL_BRIEF_MODEL', 'gpt-5.4-mini'),                # 心が「今のまとめ」を書く（mind.py）
    'stt': ('CIEL_STT_MODEL', 'gpt-live-transcribe'),             # 文字起こし（CIEL_MODEL=pipeline。話している途中から文字が出て、名前のヒントを渡せる）
    'thought': ('CIEL_THOUGHT_MODEL', 'gpt-5.4-mini'),            # 内なる考え（initiative.py）
    'minutes_live': ('CIEL_MINUTES_LIVE_MODEL', 'gpt-5.4-mini'),  # 議事録のライブ（minutes.py）
    'minutes': ('CIEL_MINUTES_MODEL', 'gpt-5.4'),                 # 議事録の清書（minutes.py）
    'notes': ('CIEL_NOTES_MODEL', 'gpt-5.4-mini'),                # メモ（notes.py）
    'relationship': ('CIEL_NOTES_MODEL', 'gpt-5.4-mini'),         # 関係（relationship.py。メモと同じモデル）
    'growth': ('CIEL_NOTES_MODEL', 'gpt-5.4-mini'),               # 出来事から育つ好み（growth.py。メモと同じモデル）
    'research': ('CIEL_RESEARCH_MODEL', 'gpt-5.4-mini'),          # 調べもの（web_research.py）
    'eyes': ('CIEL_EYES_MODEL', 'gpt-5.4-mini'),                  # 見せてもらった画像の説明文（eyes.py）
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


# ローカル LLM（server/local-llm。docs/operations/local-runtime-ja.md）。CIEL_LOCAL_ROLES に書いた役目だけ、OpenAI ではなくここへ送る。
# 裏で動く役目（内なる考え・まとめ・メモ・関係・育つ好み）向け：少し遅れても会話は止まらない（1 回 13〜50 秒）
LOCAL_URL = os.environ.get('CIEL_LOCAL_LLM_URL', 'http://127.0.0.1:8094/v1' if LOCAL_TEST else '').strip()
LOCAL_ROLES = {r.strip() for r in os.environ.get('CIEL_LOCAL_ROLES', '').split(',') if r.strip()}
OPENAI_ROLES = {r.strip() for r in os.environ.get('CIEL_OPENAI_ROLES', '').split(',') if r.strip()}
LOCAL_MODEL = os.environ.get('CIEL_LOCAL_LLM_MODEL', 'local')             # llama-server の --alias
LOCAL_TIMEOUT = float(os.environ.get('CIEL_LOCAL_TIMEOUT', '90'))           # 1 回の上限（秒）。歌を聴くあいだは CPU の形で遅い
_local_client = None
CHAT_ROLES = frozenset(ROLES) - {'talk', 'stt', 'research'}
if OPENAI_ROLES - CHAT_ROLES:
    raise ValueError('CIEL_OPENAI_ROLES contains unsupported roles: ' + ', '.join(sorted(OPENAI_ROLES - CHAT_ROLES)))
BACKGROUND_ROLES = {'thought', 'brief', 'notes', 'relationship', 'growth', 'minutes', 'minutes_live'}
if LOCAL_TEST and not LOCAL_URL:
    raise ValueError('CIEL_LOCAL_LLM_URL is required for local backend')


def is_local(role: str) -> bool:
    # Explicit cloud routing wins without changing local STT/service policies.
    return role not in OPENAI_ROLES and bool(LOCAL_URL) and (role in LOCAL_ROLES or (LOCAL_TEST and role in CHAT_ROLES))


def create_client(role: str):
    """役目ごとの所有クライアント。ローカルなら OpenAI のキーも不要。"""
    import openai
    if is_local(role):
        return openai.AsyncOpenAI(base_url=LOCAL_URL, api_key='local', max_retries=0)
    return openai.AsyncOpenAI()


def reply_options(reasoning_effort: str) -> dict:
    """LiveKit の LLM コンストラクター用（道具・ストリーミングも同じ接続先）。"""
    if not is_local('mind'):
        return {'model': model('mind'), 'reasoning_effort': reasoning_effort}
    import httpx
    import inference_trace
    return {'model': LOCAL_MODEL, 'base_url': LOCAL_URL, 'api_key': 'local',
            **inference_trace.client_options(),
            'timeout': httpx.Timeout(LOCAL_TIMEOUT), 'max_retries': 0,
            'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}


def model(role: str) -> str:
    if role == 'stt':
        import speech_input
        if speech_input.settings(LOCAL_TEST)[1] == 'whisper':
            return 'faster-whisper:' + os.environ.get('CIEL_WHISPER_MODEL_PATH', '/models-whisper/small').rstrip('/').rsplit('/', 1)[-1]
        if speech_input.settings(LOCAL_TEST)[1] == 'vosk':
            return 'vosk:' + os.environ.get('CIEL_VOSK_MODEL_PATH', '/models/vosk-model-small-ja-0.22').rstrip('/').rsplit('/', 1)[-1]
    if is_local(role):
        return LOCAL_MODEL
    env, default = ROLES[role]
    return os.environ.get(env, default)


async def background_completion(client, **kwargs):
    """Collect JSON/text privately while keeping the HTTP stream cancellable."""
    kwargs = {**kwargs, 'stream': True, 'stream_options': {'include_usage': True}}
    stream = await client.chat.completions.create(**kwargs)
    content, usage = [], None
    try:
        async for chunk in stream:
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.choices and chunk.choices[0].delta.content:
                content.append(chunk.choices[0].delta.content)
    finally:
        await stream.close()
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=''.join(content)))], usage=usage)


def client_for(role: str, default):
    """その役目の呼び先（ローカルなら llama-server の OpenAI 互換の窓口。そうでなければ default をそのまま）"""
    global _local_client
    if not is_local(role):
        return default
    if _local_client is None:
        import openai
        _local_client = openai.AsyncOpenAI(base_url=LOCAL_URL, api_key='local', max_retries=0)
    if role in BACKGROUND_ROLES and os.environ.get('CIEL_VOICE_FAST', '1') == '1':
        async def create(**kwargs):
            async def operation(**values):
                return await background_completion(_local_client, **values)
            return await inference_activity.activity.run(operation, **kwargs)
        return SimpleNamespace(base_url=_local_client.base_url,
                               chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return _local_client


def options(role: str, **kwargs) -> dict:
    """chat.completions.create の引数を、その役目の呼び先に合わせる。ローカルなら：モデルの名前を替え、考える段（thinking）を
    切り（Qwen3.5 は切らないと、書ける量を考える段に使い切って答えが空になった）、reasoning_effort は送らず、時間の上限を延ばす"""
    debug_log.record('model_request', role=role, model=model(role))
    if not is_local(role):
        return kwargs
    kwargs = dict(kwargs)
    kwargs['model'] = LOCAL_MODEL
    kwargs.pop('reasoning_effort', None)
    kwargs['timeout'] = max(float(kwargs.get('timeout') or 0), LOCAL_TIMEOUT)
    extra = dict(kwargs.get('extra_body') or {})
    extra['chat_template_kwargs'] = {'enable_thinking': False}
    kwargs['extra_body'] = extra
    background = role in BACKGROUND_ROLES
    headers = dict(kwargs.get('extra_headers') or {})
    headers['X-Ciel-Work-Class'] = ('background' if background and os.environ.get('CIEL_VOICE_FAST', '1') == '1'
                                    else 'foreground')
    kwargs['extra_headers'] = headers
    return kwargs


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


async def vision_available(role='mind') -> bool:
    """Discover local vision support; never silently route an image to a cloud model."""
    if not is_local(role):
        return True
    import httpx
    root = LOCAL_URL.rstrip('/')
    if root.endswith('/v1'):
        root = root[:-3]
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(root + '/props')
            response.raise_for_status()
            return response.json().get('modalities', {}).get('vision') is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False
