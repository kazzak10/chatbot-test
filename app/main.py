"""
Chatbot vocal pour restaurant - Point d'entrée principal.

Architecture (multi-restaurants via JSON) :
1. Twilio reçoit l'appel sur un numéro et envoie un webhook vers /voice
   avec le paramètre "To" = numéro appelé
2. On charge les infos du restaurant correspondant depuis data/restaurants.json
3. On répond avec un message d'accueil personnalisé + on écoute l'appelant
4. Twilio transcrit la voix et renvoie le texte vers /process
5. On envoie le texte à GPT (avec le contexte du bon restaurant) pour une réponse
6. On répond à l'appelant avec la réponse vocale, et on boucle la conversation
"""

import os
import json
from pathlib import Path
from fastapi import FastAPI, Form
from fastapi.responses import Response
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Chemin vers le fichier JSON contenant les infos de chaque restaurant
RESTAURANTS_FILE = Path(__file__).parent / "data" / "restaurants.json"

# Restaurant par défaut si le numéro appelé n'est pas trouvé dans le JSON
DEFAULT_RESTAURANT = {
    "name": "notre restaurant",
    "hours": "non renseignées",
    "address": "non renseignée",
    "specialties": "non renseignées",
    "reservation_email": "",
}


def load_restaurants() -> dict:
    """Charge le fichier JSON des restaurants à chaque requête (simple, pas de cache pour l'instant)."""
    with open(RESTAURANTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_restaurant_by_number(phone_number: str) -> dict:
    """Récupère les infos du restaurant correspondant au numéro Twilio appelé."""
    restaurants = load_restaurants()
    return restaurants.get(phone_number, DEFAULT_RESTAURANT)


def build_system_prompt(restaurant: dict) -> str:
    """Construit le prompt système GPT personnalisé pour ce restaurant."""
    return f"""Tu es l'assistant vocal téléphonique de {restaurant['name']}.
Tu réponds aux appelants de façon brève, naturelle et chaleureuse (2-3 phrases max, car c'est de la voix).

Informations du restaurant :
- Horaires : {restaurant['hours']}
- Adresse : {restaurant['address']}
- Spécialités : {restaurant.get('specialties', 'non renseignées')}

Si on te demande une réservation, demande la date, l'heure et le nombre de personnes.
Si tu ne sais pas répondre à une question, propose de transférer l'appel à un humain.
Ne dis jamais que tu es une IA sauf si on te le demande explicitement.
"""


@app.post("/voice")
async def voice_webhook(To: str = Form(default="")):
    """
    Premier point d'entrée : Twilio appelle cette route quand quelqu'un compose le numéro.
    'To' = le numéro Twilio qui a été appelé, ça nous permet de savoir quel restaurant répond.
    """
    restaurant = get_restaurant_by_number(To)

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        <Say voice="Polly.Lea" language="fr-FR">
            Bonjour, bienvenue chez {restaurant['name']}. Comment puis-je vous aider ?
        </Say>
    </Gather>
    <Say voice="Polly.Lea" language="fr-FR">Je n'ai rien entendu, au revoir.</Say>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/process")
async def process_speech(SpeechResult: str = Form(default=""), To: str = Form(default="")):
    """
    Twilio nous envoie ici le texte transcrit de ce que l'appelant a dit,
    ainsi que le numéro appelé pour qu'on sache quel restaurant contextualiser.
    """
    restaurant = get_restaurant_by_number(To)
    user_text = SpeechResult.strip()

    if not user_text:
        reply_text = "Désolé, je n'ai pas compris. Pouvez-vous répéter ?"
    else:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_system_prompt(restaurant)},
                {"role": "user", "content": user_text},
            ],
            max_tokens=150,
        )
        reply_text = completion.choices[0].message.content

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        <Say voice="Polly.Lea" language="fr-FR">{reply_text}</Say>
    </Gather>
    <Say voice="Polly.Lea" language="fr-FR">Au revoir, à bientôt chez {restaurant['name']}.</Say>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "chatbot-vocal-restaurant"}


@app.get("/restaurants")
async def list_restaurants():
    """Endpoint utilitaire pour vérifier facilement quels restaurants sont configurés."""
    return load_restaurants()