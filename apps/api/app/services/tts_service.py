from __future__ import annotations

import base64
import math
import wave
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import AUDIO_DIR
from app.core.schemas import TTSRequest, TTSResponse
from app.core.config import settings
from app.services.model_provider import normalize_mimo_model_name


def get_tts_runtime_source() -> str:
    return "mimo" if settings.mimo_base_url and settings.mimo_api_key else "stub"


def _build_local_tts(request: TTSRequest) -> TTSResponse:
    filename = f"tts_{uuid4().hex}.wav"
    target = AUDIO_DIR / filename
    sample_rate = 22050
    duration_seconds = min(max(len(request.input) / 18, 1.0), 8.0)
    amplitude = 8000
    frequency = 440 if "female" in request.voice else 330

    with wave.open(str(target), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for i in range(int(sample_rate * duration_seconds)):
            value = int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate)))
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))

    return TTSResponse(
        model=request.model,
        audio_url=f"/static/audio/{filename}",
        duration=round(duration_seconds, 2),
        source="stub",
    )


async def _build_mimo_tts(request: TTSRequest) -> TTSResponse:
    normalized_model = normalize_mimo_model_name(request.model)
    payload = {
        "model": normalized_model,
        "messages": [{"role": "assistant", "content": request.input}],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.mimo_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.mimo_timeout_seconds) as client:
        response = await client.post(
            f"{settings.mimo_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    message = data.get("choices", [{}])[0].get("message", {})
    audio_payload = message.get("audio", {})
    audio_data = audio_payload.get("data")
    if not audio_data:
        raise ValueError("MiMo TTS response does not contain audio data")

    audio_bytes = base64.b64decode(audio_data)
    filename = f"tts_{uuid4().hex}.wav"
    target = AUDIO_DIR / filename
    target.write_bytes(audio_bytes)
    duration_seconds = min(max(len(request.input) / 18, 1.0), 30.0)

    return TTSResponse(
        model=request.model,
        audio_url=f"/static/audio/{filename}",
        duration=round(duration_seconds, 2),
        source="mimo",
    )


async def synthesize_tts(request: TTSRequest) -> TTSResponse:
    if settings.mimo_base_url and settings.mimo_api_key:
        try:
            return await _build_mimo_tts(request)
        except Exception:
            return _build_local_tts(request)
    return _build_local_tts(request)
