"""
Chatbot vocal pour restaurant - Version avec transfert d'appel réel.

Architecture :
1. Twilio reçoit l'appel → /voice (accueil + écoute)
2. Twilio transcrit la voix → /process (GPT répond)
3. Si GPT répond TRANSFER → <Dial> vers le numéro du gérant
4. Sinon → boucle de conversation avec mémoire courte par appel
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Form
from fastapi.responses import Response
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("chatbot")

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DATA_DIR = Path(__file__).parent / "data"
RESTAURANTS_FILE = DATA_DIR / "restaurants.json"
RESERVATIONS_FILE = DATA_DIR / "reservations.json"

DEFAULT_RESTAURANT = {"name": "notre restaurant", "hours": {}, "address": {}, "menu": {}}

# Historique court par appel { call_sid: [{"role": ..., "content": ...}] }
call_sessions: dict[str, list[dict]] = {}
MAX_HISTORY_TURNS = 6

# Mots-clés qui déclenchent un transfert immédiat sans passer par GPT
TRANSFER_KEYWORDS = [
    "allergie", "allergique", "urgence", "urgent",
    "plainte", "réclamation", "intoxication", "accident",
    "parler à quelqu'un", "parler à une personne", "gérant", "manager",
    "responsable", "je veux un humain",
]


# ─── Chargement des données ───────────────────────────────────────────────────

def load_restaurants() -> dict:
    with open(RESTAURANTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_restaurant_by_number(phone_number: str) -> dict:
    restaurants = load_restaurants()
    restaurant = restaurants.get(phone_number)
    if not restaurant:
        logger.warning(f"[WARNING] Numéro {phone_number!r} non trouvé dans le JSON → restaurant par défaut")
        return DEFAULT_RESTAURANT
    return restaurant


# ─── Formatage des données pour le prompt ────────────────────────────────────

def format_address(address: dict) -> str:
    if not address:
        return "non renseignée"
    return f"{address.get('street', '')}, {address.get('postal_code', '')} {address.get('city', '')}"


def format_hours(hours: dict) -> str:
    if not hours:
        return "non renseignées"
    jours_fr = {
        "monday": "Lundi", "tuesday": "Mardi", "wednesday": "Mercredi",
        "thursday": "Jeudi", "friday": "Vendredi", "saturday": "Samedi", "sunday": "Dimanche",
    }
    return " | ".join(f"{jours_fr.get(k, k)}: {v}" for k, v in hours.items())


def format_menu(menu: dict) -> str:
    if not menu:
        return "non renseigné"
    parts = []
    for category in ["starters", "mains", "desserts"]:
        items = menu.get(category, [])
        if items:
            label = {"starters": "Entrées", "mains": "Plats", "desserts": "Desserts"}[category]
            items_str = ", ".join(f"{i['name']} ({i['price']})" for i in items)
            parts.append(f"{label}: {items_str}")
    mdj = menu.get("menu_du_jour", {})
    if mdj and mdj.get("price"):
        parts.append(
            f"Menu du jour ({mdj.get('description', '')}) à {mdj['price']}, "
            f"disponible {mdj.get('available', '')}"
        )
    return " / ".join(parts) if parts else "non renseigné"


def build_system_prompt(restaurant: dict) -> str:
    name = restaurant.get("name", "notre restaurant")
    tagline = restaurant.get("tagline", "")
    address = format_address(restaurant.get("address", {}))
    hours = format_hours(restaurant.get("hours", {}))
    menu = format_menu(restaurant.get("menu", {}))
    cuisine = restaurant.get("cuisine_type", "non renseigné")
    price_range = restaurant.get("price_range", "non renseigné")
    reservation_required = "oui" if restaurant.get("reservation_required") else "non, mais recommandée"
    parking = restaurant.get("parking", "non renseigné")
    accessibility = restaurant.get("accessibility", "non renseigné")
    pet_friendly = "oui" if restaurant.get("pet_friendly") else "non"
    outdoor = "oui" if restaurant.get("outdoor_seating") else "non"
    payment = ", ".join(restaurant.get("payment_methods", [])) or "non renseigné"
    notes = restaurant.get("special_notes", "")

    return f"""Tu es l'assistant vocal téléphonique de {name}. {tagline}

Tu réponds aux appelants de façon brève, naturelle et chaleureuse (2-3 phrases max, car c'est de la voix).

Informations du restaurant :
- Adresse : {address}
- Horaires : {hours}
- Type de cuisine : {cuisine}
- Gamme de prix : {price_range}
- Menu : {menu}
- Réservation : {reservation_required}
- Parking : {parking}
- Accessibilité PMR : {accessibility}
- Animaux acceptés : {pet_friendly}
- Terrasse : {outdoor}
- Moyens de paiement : {payment}
- Notes : {notes}

RÈGLES IMPORTANTES :
1. Si on te demande une réservation, demande la date, l'heure et le nombre de personnes UNE INFO À LA FOIS.
   Une fois les 3 infos obtenues, confirme : "Je confirme : une table pour [X] personnes le [date] à [heure]. C'est bien ça ?"

2. La transcription vocale peut contenir de légères erreurs. Si tu devines la question malgré tout, réponds-y directement.

3. Si la demande dépasse ce que tu peux gérer (événement privé, commande volumineuse, partenariat, demande inhabituelle...),
   réponds UNIQUEMENT par le mot : TRANSFER

4. Si tu n'as vraiment pas l'information demandée et qu'elle est importante,
   réponds UNIQUEMENT par le mot : TRANSFER

5. Ne dis jamais que tu es une IA sauf si on te le demande explicitement.
6. Ne parle jamais des outils ou technologies utilisés.
"""


# ─── Gestion de la mémoire par appel ─────────────────────────────────────────

def get_call_history(call_sid: str) -> list[dict]:
    return call_sessions.get(call_sid, [])


def add_to_history(call_sid: str, role: str, content: str) -> None:
    history = call_sessions.setdefault(call_sid, [])
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_TURNS * 2:
        call_sessions[call_sid] = history[-MAX_HISTORY_TURNS * 2:]


def clear_call_history(call_sid: str) -> None:
    call_sessions.pop(call_sid, None)


def detect_repeated_question(call_sid: str, user_text: str) -> bool:
    """Filet de sécurité : si l'utilisateur répète 2 fois la même chose → transfert."""
    history = get_call_history(call_sid)
    user_messages = [m["content"].lower() for m in history if m["role"] == "user"]
    return user_messages.count(user_text.lower()) >= 2


# ─── Détection de transfert immédiat (sans GPT) ───────────────────────────────

def needs_immediate_transfer(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TRANSFER_KEYWORDS)


# ─── Réservations ─────────────────────────────────────────────────────────────

def save_reservation(call_sid: str, restaurant_name: str, confirmation_text: str) -> None:
    reservations = []
    if RESERVATIONS_FILE.exists():
        with open(RESERVATIONS_FILE, encoding="utf-8") as f:
            reservations = json.load(f)
    reservations.append({
        "call_sid": call_sid,
        "restaurant": restaurant_name,
        "confirmation_text": confirmation_text,
        "timestamp": datetime.now().isoformat(),
    })
    with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(reservations, f, ensure_ascii=False, indent=2)


# ─── TwiML helpers ────────────────────────────────────────────────────────────

def twiml_say_and_listen(message: str, restaurant_name: str) -> str:
    """Répond vocalement et relance l'écoute pour continuer la conversation."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/process" language="fr-FR" speechTimeout="auto">
        <Say voice="Polly.Lea" language="fr-FR">{message}</Say>
    </Gather>
    <Say voice="Polly.Lea" language="fr-FR">Au revoir, à bientôt chez {restaurant_name}.</Say>
</Response>"""


def twiml_transfer(manager_phone: str, transfer_message: str) -> str:
    """Annonce le transfert et compose le numéro du gérant via <Dial>."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Lea" language="fr-FR">{transfer_message}</Say>
    <Dial timeout="30" action="/transfer-complete">
        <Number>{manager_phone}</Number>
    </Dial>
    <Say voice="Polly.Lea" language="fr-FR">Notre équipe n'est pas disponible pour le moment. Merci de rappeler ou laissez-nous un message.</Say>
</Response>"""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.post("/voice")
async def voice_webhook(To: str = Form(default=""), CallSid: str = Form(default="")):
    """Entrée d'un nouvel appel. Démarre une session propre et accueille le client."""
    restaurant = get_restaurant_by_number(To)
    clear_call_history(CallSid)
    logger.info(f"[APPEL] CallSid={CallSid} | To={To} | Restaurant={restaurant.get('name')}")

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
async def process_speech(
    SpeechResult: str = Form(default=""),
    To: str = Form(default=""),
    CallSid: str = Form(default=""),
):
    restaurant = get_restaurant_by_number(To)
    user_text = SpeechResult.strip()
    manager_phone = restaurant.get("manager_phone", "")

    logger.info(f"[PROCESS] CallSid={CallSid} | Transcription='{user_text}'")
    logger.info(f"[PROCESS] Historique={len(get_call_history(CallSid))} messages")

    # Cas 1 : transcription vide
    if not user_text:
        logger.info("[PROCESS] Transcription vide → demande de répétition")
        return Response(
            content=twiml_say_and_listen("Désolé, je n'ai pas compris. Pouvez-vous répéter ?", restaurant["name"]),
            media_type="application/xml"
        )

    # Cas 2 : transfert immédiat par mot-clé (allergie, gérant, urgence...)
    if needs_immediate_transfer(user_text):
        logger.info(f"[PROCESS] Mot-clé transfert détecté → transfert direct vers {manager_phone}")
        if manager_phone:
            return Response(
                content=twiml_transfer(manager_phone, "Je vous transfère immédiatement à notre équipe."),
                media_type="application/xml"
            )
        else:
            return Response(
                content=twiml_say_and_listen(
                    "Je comprends, malheureusement notre équipe n'est pas joignable en ce moment. Merci de rappeler directement.",
                    restaurant["name"]
                ),
                media_type="application/xml"
            )

    # Cas 3 : filet de sécurité — même question répétée 2 fois
    if detect_repeated_question(CallSid, user_text):
        logger.info(f"[PROCESS] Question répétée 2 fois → transfert vers {manager_phone}")
        if manager_phone:
            return Response(
                content=twiml_transfer(manager_phone, "Je vais vous passer un membre de notre équipe qui pourra mieux vous aider."),
                media_type="application/xml"
            )

    # Cas 4 : appel à GPT
    add_to_history(CallSid, "user", user_text)
    history = get_call_history(CallSid)
    messages = [{"role": "system", "content": build_system_prompt(restaurant)}] + history

    logger.info(f"[PROCESS] Appel GPT avec {len(messages)} messages")
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=150,
    )
    reply_text = completion.choices[0].message.content.strip()
    logger.info(f"[PROCESS] Réponse GPT: '{reply_text}'")

    # Cas 5 : GPT demande un transfert
    if reply_text.upper() == "TRANSFER" or reply_text.upper().startswith("TRANSFER"):
        logger.info(f"[PROCESS] GPT a répondu TRANSFER → transfert vers {manager_phone}")
        if manager_phone:
            return Response(
                content=twiml_transfer(
                    manager_phone,
                    "Je n'ai pas l'information pour répondre à votre demande. Je vous passe directement quelqu'un de l'équipe."
                ),
                media_type="application/xml"
            )
        else:
            reply_text = "Je n'ai pas cette information. Je vous invite à rappeler directement l'équipe ou à envoyer un email."
            return Response(
                content=twiml_say_and_listen(reply_text, restaurant["name"]),
                media_type="application/xml"
            )

    # Cas 6 : réponse normale, on l'ajoute à l'historique
    add_to_history(CallSid, "assistant", reply_text)

    if "je confirme" in reply_text.lower():
        save_reservation(CallSid, restaurant["name"], reply_text)
        logger.info(f"[PROCESS] Réservation sauvegardée | CallSid={CallSid}")

    return Response(
        content=twiml_say_and_listen(reply_text, restaurant["name"]),
        media_type="application/xml"
    )


@app.post("/transfer-complete")
async def transfer_complete(DialCallStatus: str = Form(default="")):
    """Appelé par Twilio quand le <Dial> se termine (raccroché, pas de réponse...)."""
    logger.info(f"[TRANSFER] Statut du transfert : {DialCallStatus}")
    return Response(
        content="""<?xml version="1.0" encoding="UTF-8"?><Response></Response>""",
        media_type="application/xml"
    )


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "chatbot-vocal-restaurant"}


@app.get("/restaurants")
async def list_restaurants():
    return load_restaurants()


@app.get("/reservations")
async def list_reservations():
    if RESERVATIONS_FILE.exists():
        with open(RESERVATIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []