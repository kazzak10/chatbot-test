"""
Synthèse vocale via Google Cloud Text-to-Speech.
L'audio est stocké en RAM par CallSid et servi via la route /audio/{call_sid}.
"""

import logging
import base64
import httpx
from app.config import GOOGLE_TTS_API_KEY

logger = logging.getLogger("chatbot")

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_TTS_ENABLED = bool(GOOGLE_TTS_API_KEY)

# Stockage temporaire de l'audio par call_sid
_audio_cache: dict[str, bytes] = {}


async def generate_and_store_audio(call_sid: str, text: str) -> bool:
    """
    Génère l'audio via Google TTS et le stocke en RAM sous la clé call_sid.
    Retourne True si succès, False si échec (fallback Polly).
    """
    if not GOOGLE_TTS_ENABLED:
        return False

    try:
        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": "fr-FR",
                "name": "fr-FR-Wavenet-C",
                "ssmlGender": "FEMALE",
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": 1.0,
                "pitch": 0.0,
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                GOOGLE_TTS_URL,
                json=payload,
                params={"key": GOOGLE_TTS_API_KEY},
            )
            response.raise_for_status()
            audio_base64 = response.json().get("audioContent", "")
            if audio_base64:
                _audio_cache[call_sid] = base64.b64decode(audio_base64)
                logger.info(f"[VOICE] Audio Google TTS stocké pour {call_sid}")
                return True
            return False

    except Exception as e:
        logger.warning(f"[VOICE] Google TTS échoué, fallback Polly : {e}")
        return False


def get_audio(call_sid: str) -> bytes | None:
    """Récupère l'audio stocké pour un call_sid."""
    return _audio_cache.pop(call_sid, None)


def is_tts_enabled() -> bool:
    return GOOGLE_TTS_ENABLED