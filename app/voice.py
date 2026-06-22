"""
Synthèse vocale via ElevenLabs.
Si ElevenLabs est configuré (clé API + voice ID dans .env), on l'utilise.
Sinon on retombe sur la voix Twilio Polly (fallback automatique).

Pour configurer ElevenLabs :
1. Crée un compte sur elevenlabs.io
2. Choisis une voix française dans la bibliothèque (ex: "Charlotte", "Matilda")
3. Copie le Voice ID depuis la page de la voix
4. Ajoute dans .env :
   ELEVENLABS_API_KEY=sk_...
   ELEVENLABS_VOICE_ID=...
"""

import logging
import httpx
import base64
from app.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger("chatbot")

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_ENABLED = bool(ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID)


async def generate_audio_base64(text: str) -> str | None:
    """
    Génère l'audio via ElevenLabs et retourne le base64 de l'audio MP3.
    Retourne None si ElevenLabs n'est pas configuré ou si la requête échoue.
    """
    if not ELEVENLABS_ENABLED:
        return None

    try:
        url = ELEVENLABS_URL.format(voice_id=ELEVENLABS_VOICE_ID)
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            audio_base64 = base64.b64encode(response.content).decode("utf-8")
            logger.info("[VOICE] Audio ElevenLabs généré avec succès")
            return audio_base64

    except Exception as e:
        logger.warning(f"[VOICE] ElevenLabs a échoué, fallback Twilio Polly : {e}")
        return None


def is_elevenlabs_enabled() -> bool:
    return ELEVENLABS_ENABLED