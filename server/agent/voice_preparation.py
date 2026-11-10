"""Prepare the actual job process before subscribing to microphone input."""
import asyncio
import hashlib
import os
import time

import aiohttp
import debug_log
import irodori_tts
import models


async def mode_snapshot():
    url = os.environ.get('CIEL_LOCAL_LLM_CONTROL', 'http://127.0.0.1:8095')
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as http:
        async with http.get(url+'/mode') as response:
            response.raise_for_status()
            value = await response.json()
    if not value.get('ready') or not value.get('generation') or value.get('generation_scope') not in ('inference_process','evaluation_ingress'):
        raise RuntimeError('Shared API is not ready or lacks generation identity')
    return {k:value[k] for k in ('model','mode','generation','generation_scope')}


async def prepare(agent, replies, encoder_task=None):
    started = time.monotonic()
    identity = await mode_snapshot()
    stages = {}
    async def stage(name, operation):
        began = time.monotonic()
        await operation()
        stages[name] = round((time.monotonic()-began)*1000, 2)
        debug_log.record('voice_prepare', stage=name, ms=stages[name])

    if encoder_task is not None:
        async def speaker():
            await encoder_task
            if replies.encoder is None:
                raise RuntimeError('Speaker encoder preparation failed')
        await stage('speaker', speaker)

    async def decoder():
        from vosk_engine import load_model
        await asyncio.to_thread(load_model, os.environ.get('CIEL_VOSK_MODEL_PATH', '/models/vosk-model-small-ja-0.22'))
    await stage('stt', decoder)
    text = agent.persona.voice_warmup.strip()
    if not text:
        raise ValueError('voice_warmup must contain speech text')
    instructions = agent.talker_instructions_for('normal', 'solo')
    async def llm():
        client = models.create_client('mind')
        try:
            await client.chat.completions.create(model=models.LOCAL_MODEL, max_tokens=1,
                messages=[{'role': 'system', 'content': instructions}, {'role': 'user', 'content': text}],
                extra_body={'chat_template_kwargs': {'enable_thinking': False}},
                extra_headers={'X-Ciel-Work-Class': 'background'}, timeout=models.LOCAL_TIMEOUT)
        finally:
            await client.close()
    await stage('llm', llm)
    async def tts():
        async with aiohttp.ClientSession() as http:
            pcm, rate = await irodori_tts.request_audio(http, {'text': text})
            if not pcm or rate <= 0:
                raise RuntimeError('Empty TTS preparation result')
    await stage('tts', tts)
    if await mode_snapshot() != identity:
        raise RuntimeError('Inference generation changed during preparation')
    return dict(v=1, type='voice.ready', ready=True, elapsed_ms=round((time.monotonic()-started)*1000, 2),
                stages=stages, inference=identity, persona_sha256=agent.persona.fingerprint,
                prefix_sha256=hashlib.sha256(instructions.encode()).hexdigest())


async def validate(readiness):
    if not readiness or not readiness.get('ready'):
        return readiness
    try:
        current = await mode_snapshot()
        if current == readiness['inference']:
            return readiness
        reason = 'inference_generation_changed'
    except Exception:
        reason = 'inference_readiness_unknown'
    return {**readiness, 'ready': False, 'reason': reason}
