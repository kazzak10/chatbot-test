"""
Construction des réponses TwiML envoyées à Twilio.
Supporte deux modes de voix :
- ElevenLabs (si configuré) : audio MP3 haute qualité via <Play>
- Twilio Polly (fallback) : voix synthétique via <Say>
"""

from app.voice import is_elevenlabs_enabled

POLLY_VOICE = "Polly.Lea"
POLLY_LANG = "fr-FR"


def _say_tag(message: str) -> str:
    """Balise <Say> avec la voix Twilio Polly."""
    return f'<Say voice="{POLLY_VOICE}" language="{POLLY_LANG}">{message}</Say>'


def _play_tag(audio_base64: str) -> str:
    """Balise <Play> avec audio ElevenLabs encodé en base64 (data URI)."""
    return f'<Play>data:audio/mpeg;base64,{audio_base64}</Play>'


def _speak(message: str, audio_base64: str | None) -> str:
    """Choisit automatiquement entre ElevenLabs et Polly."""
    if audio_base64:
        return _play_tag(audio_base64)
    return _say_tag(message)


def say_and_listen(message: str, restaurant_name: str, audio_base64: str | None = None) -> str:
    """Répond vocalement et relance l'écoute pour continuer la conversation."""
    speak = _speak(message, audio_base64)
    goodbye = _say_tag(f"Au revoir, à bientôt chez {restaurant_name}.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        {speak}
    </Gather>
    {goodbye}
</Response>"""


def say_transfer(manager_phone: str, message: str, audio_base64: str | None = None) -> str:
    """Annonce le transfert et compose le numéro du gérant via <Dial>."""
    speak = _speak(message, audio_base64)
    unavailable = _say_tag("Notre équipe n'est pas disponible pour le moment. Merci de rappeler.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {speak}
    <Dial timeout="30" action="/transfer-complete">
        <Number>{manager_phone}</Number>
    </Dial>
    {unavailable}
</Response>"""


def say_welcome(restaurant_name: str, audio_base64: str | None = None) -> str:
    """Message d'accueil au début de l'appel."""
    message = f"Bonjour, bienvenue chez {restaurant_name}. Comment puis-je vous aider ?"
    speak = _speak(message, audio_base64)
    silence = _say_tag("Je n'ai rien entendu, au revoir.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        {speak}
    </Gather>
    {silence}
</Response>"""