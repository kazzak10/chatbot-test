"""
Construction des réponses TwiML envoyées à Twilio.
Supporte deux modes :
- Google TTS (si configuré) : URL vers /audio/{call_sid} via <Play>
- Twilio Polly (fallback) : voix synthétique via <Say>
"""

POLLY_VOICE = "Polly.Lea"
POLLY_LANG = "fr-FR"


def _say_tag(message: str) -> str:
    return f'<Say voice="{POLLY_VOICE}" language="{POLLY_LANG}">{message}</Say>'


def _play_tag(audio_url: str) -> str:
    return f'<Play>{audio_url}</Play>'


def _speak(message: str, audio_url: str | None) -> str:
    if audio_url:
        return _play_tag(audio_url)
    return _say_tag(message)


def say_and_listen(message: str, restaurant_name: str, audio_url: str | None = None) -> str:
    speak = _speak(message, audio_url)
    goodbye = _say_tag(f"Au revoir, à bientôt chez {restaurant_name}.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        {speak}
    </Gather>
    {goodbye}
</Response>"""


def say_transfer(manager_phone: str, message: str, audio_url: str | None = None) -> str:
    speak = _speak(message, audio_url)
    unavailable = _say_tag("Notre équipe n'est pas disponible pour le moment. Merci de rappeler.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {speak}
    <Dial timeout="30" action="/transfer-complete">
        <Number>{manager_phone}</Number>
    </Dial>
    {unavailable}
</Response>"""


def say_welcome(restaurant_name: str, audio_url: str | None = None) -> str:
    message = f"Bonjour, bienvenue chez {restaurant_name}. Comment puis-je vous aider ?"
    speak = _speak(message, audio_url)
    silence = _say_tag("Je n'ai rien entendu, au revoir.")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        {speak}
    </Gather>
    {silence}
</Response>"""