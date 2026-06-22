"""
Chatbot vocal pour restaurant - Point d'entrée FastAPI.

Ce fichier ne contient que les routes HTTP.
Toute la logique métier est dans les modules dédiés :
- restaurant.py  → données et prompt
- memory.py      → historique de conversation
- transfer.py    → détection et déclenchement du transfert
- twiml.py       → construction des réponses Twilio
- voice.py       → synthèse vocale ElevenLabs
- reservations.py → sauvegarde des réservations
"""

import logging
from fastapi import FastAPI, Form
from fastapi.responses import Response
from openai import OpenAI

from app.config import OPENAI_API_KEY, GPT_MODEL, GPT_MAX_TOKENS
from app import memory, reservations, transfer
from app.restaurant import get_restaurant_by_number, build_system_prompt
from app.twiml import say_and_listen, say_transfer, say_welcome
from app.voice import generate_audio_base64

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("chatbot")

app = FastAPI()
gpt = OpenAI(api_key=OPENAI_API_KEY)


@app.post("/voice")
async def voice_webhook(To: str = Form(default=""), CallSid: str = Form(default="")):
    """Entrée d'un nouvel appel : démarre une session propre et accueille le client."""
    restaurant = get_restaurant_by_number(To)
    memory.clear(CallSid)
    logger.info(f"[APPEL] CallSid={CallSid} | To={To} | Restaurant={restaurant.get('name')}")

    audio = await generate_audio_base64(
        f"Bonjour, bienvenue chez {restaurant['name']}. Comment puis-je vous aider ?"
    )
    return Response(
        content=say_welcome(restaurant["name"], audio),
        media_type="application/xml"
    )


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
    logger.info(f"[PROCESS] Historique={len(memory.get_history(CallSid))} messages")

    # Cas 1 : transcription vide
    if not user_text:
        audio = await generate_audio_base64("Désolé, je n'ai pas compris. Pouvez-vous répéter ?")
        return Response(
            content=say_and_listen("Désolé, je n'ai pas compris. Pouvez-vous répéter ?", restaurant["name"], audio),
            media_type="application/xml"
        )

    # Cas 2 : mot-clé transfert immédiat (allergie, gérant, urgence...)
    if transfer.needs_immediate_transfer(user_text):
        logger.info(f"[TRANSFER] Mot-clé détecté → transfert vers {manager_phone}")
        msg = "Je vous transfère immédiatement à notre équipe."
        audio = await generate_audio_base64(msg)
        if manager_phone:
            return Response(content=say_transfer(manager_phone, msg, audio), media_type="application/xml")
        msg_no_phone = "Je comprends, notre équipe n'est pas joignable en ce moment. Merci de rappeler directement."
        audio = await generate_audio_base64(msg_no_phone)
        return Response(content=say_and_listen(msg_no_phone, restaurant["name"], audio), media_type="application/xml")

    # Cas 3 : question répétée 2 fois (filet de sécurité)
    if memory.is_repeated(CallSid, user_text) and manager_phone:
        logger.info(f"[TRANSFER] Question répétée → transfert vers {manager_phone}")
        msg = "Je vais vous passer un membre de notre équipe qui pourra mieux vous aider."
        audio = await generate_audio_base64(msg)
        return Response(content=say_transfer(manager_phone, msg, audio), media_type="application/xml")

    # Cas 4 : appel GPT
    memory.add_message(CallSid, "user", user_text)
    messages = [{"role": "system", "content": build_system_prompt(restaurant)}] + memory.get_history(CallSid)

    logger.info(f"[GPT] Appel avec {len(messages)} messages")
    completion = gpt.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_tokens=GPT_MAX_TOKENS,
    )
    reply = completion.choices[0].message.content.strip()
    logger.info(f"[GPT] Réponse : '{reply}'")

    # Cas 5 : GPT demande un transfert
    if transfer.is_transfer_response(reply):
        logger.info(f"[TRANSFER] GPT a répondu TRANSFER → transfert vers {manager_phone}")
        msg = "Je n'ai pas l'information pour répondre. Je vous passe quelqu'un de l'équipe."
        audio = await generate_audio_base64(msg)
        if manager_phone:
            return Response(content=say_transfer(manager_phone, msg, audio), media_type="application/xml")
        msg_no_phone = "Je n'ai pas cette information. Merci de rappeler directement l'équipe."
        audio = await generate_audio_base64(msg_no_phone)
        return Response(content=say_and_listen(msg_no_phone, restaurant["name"], audio), media_type="application/xml")

    # Cas 6 : réponse normale
    memory.add_message(CallSid, "assistant", reply)

    if "je confirme" in reply.lower():
        reservations.save(CallSid, restaurant["name"], reply)

    audio = await generate_audio_base64(reply)
    return Response(
        content=say_and_listen(reply, restaurant["name"], audio),
        media_type="application/xml"
    )


@app.post("/transfer-complete")
async def transfer_complete(DialCallStatus: str = Form(default="")):
    """Appelé par Twilio quand le <Dial> se termine."""
    logger.info(f"[TRANSFER] Statut : {DialCallStatus}")
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml"
    )


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "chatbot-vocal-restaurant"}


@app.get("/restaurants")
async def list_restaurants():
    from app.restaurant import load_restaurants
    return load_restaurants()


@app.get("/reservations")
async def list_reservations():
    return reservations.get_all()