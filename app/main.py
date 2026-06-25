"""
Chatbot vocal pour restaurant - Point d'entrée FastAPI.
Ce fichier ne contient que les routes HTTP.
"""

import logging
from fastapi import FastAPI, Form, Request
from fastapi.responses import Response
from openai import OpenAI

from app.config import OPENAI_API_KEY, GPT_MODEL, GPT_MAX_TOKENS
from app import memory, reservations, transfer
from app.restaurant import get_restaurant_by_number, build_system_prompt, load_restaurants
from app.twiml import say_and_listen, say_transfer, say_welcome
from app.voice import generate_and_store_audio, get_audio, is_tts_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("chatbot")

app = FastAPI()
gpt = OpenAI(api_key=OPENAI_API_KEY)


def _get_base_url(request: Request) -> str:
    """Retourne l'URL de base du serveur (ngrok ou prod)."""
    return str(request.base_url).rstrip("/")


async def _prepare_audio(call_sid: str, text: str, request: Request) -> str | None:
    """Génère l'audio et retourne l'URL publique, ou None si fallback Polly."""
    success = await generate_and_store_audio(call_sid, text)
    if success:
        return f"{_get_base_url(request)}/audio/{call_sid}"
    return None


@app.get("/audio/{call_sid}")
async def serve_audio(call_sid: str):
    """Sert le fichier MP3 généré par Google TTS à Twilio."""
    audio = get_audio(call_sid)
    if not audio:
        return Response(status_code=404)
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/voice")
async def voice_webhook(request: Request, To: str = Form(default=""), CallSid: str = Form(default="")):
    """Entrée d'un nouvel appel."""
    restaurant = get_restaurant_by_number(To)
    memory.clear(CallSid)
    logger.info(f"[APPEL] CallSid={CallSid} | To={To} | Restaurant={restaurant.get('name')}")

    welcome_text = f"Bonjour, bienvenue chez {restaurant['name']}. Comment puis-je vous aider ?"
    audio_url = await _prepare_audio(CallSid, welcome_text, request)
    return Response(content=say_welcome(restaurant["name"], audio_url), media_type="application/xml")


@app.post("/process")
async def process_speech(
    request: Request,
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
        msg = "Désolé, je n'ai pas compris. Pouvez-vous répéter ?"
        audio_url = await _prepare_audio(CallSid, msg, request)
        return Response(content=say_and_listen(msg, restaurant["name"], audio_url), media_type="application/xml")

    # Cas 2 : mot-clé transfert immédiat
    if transfer.needs_immediate_transfer(user_text):
        logger.info(f"[TRANSFER] Mot-clé détecté → {manager_phone}")
        msg = "Je vous transfère immédiatement à notre équipe."
        audio_url = await _prepare_audio(CallSid, msg, request)
        if manager_phone:
            return Response(content=say_transfer(manager_phone, msg, audio_url), media_type="application/xml")
        msg = "Notre équipe n'est pas joignable en ce moment. Merci de rappeler directement."
        audio_url = await _prepare_audio(CallSid, msg, request)
        return Response(content=say_and_listen(msg, restaurant["name"], audio_url), media_type="application/xml")

    # Cas 3 : question répétée 2 fois
    if memory.is_repeated(CallSid, user_text) and manager_phone:
        logger.info(f"[TRANSFER] Question répétée → {manager_phone}")
        msg = "Je vais vous passer un membre de notre équipe qui pourra mieux vous aider."
        audio_url = await _prepare_audio(CallSid, msg, request)
        return Response(content=say_transfer(manager_phone, msg, audio_url), media_type="application/xml")

    # Cas 4 : appel GPT
    memory.add_message(CallSid, "user", user_text)
    messages = [{"role": "system", "content": build_system_prompt(restaurant)}] + memory.get_history(CallSid)

    logger.info(f"[GPT] Appel avec {len(messages)} messages")
    completion = gpt.chat.completions.create(
        model=GPT_MODEL, messages=messages, max_tokens=GPT_MAX_TOKENS,
    )
    reply = completion.choices[0].message.content.strip()
    logger.info(f"[GPT] Réponse : '{reply}'")

    # Cas 5 : GPT demande un transfert
    if transfer.is_transfer_response(reply):
        logger.info(f"[TRANSFER] GPT → {manager_phone}")
        msg = "Je n'ai pas l'information pour répondre. Je vous passe quelqu'un de l'équipe."
        audio_url = await _prepare_audio(CallSid, msg, request)
        if manager_phone:
            return Response(content=say_transfer(manager_phone, msg, audio_url), media_type="application/xml")
        msg = "Je n'ai pas cette information. Merci de rappeler directement l'équipe."
        audio_url = await _prepare_audio(CallSid, msg, request)
        return Response(content=say_and_listen(msg, restaurant["name"], audio_url), media_type="application/xml")

    # Cas 6 : réponse normale
    memory.add_message(CallSid, "assistant", reply)
    if "je confirme" in reply.lower():
        reservations.save(CallSid, restaurant["name"], reply)

    audio_url = await _prepare_audio(CallSid, reply, request)
    return Response(content=say_and_listen(reply, restaurant["name"], audio_url), media_type="application/xml")


@app.post("/transfer-complete")
async def transfer_complete(DialCallStatus: str = Form(default="")):
    logger.info(f"[TRANSFER] Statut : {DialCallStatus}")
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml"
    )


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "chatbot-vocal-restaurant"}


@app.get("/restaurants")
async def list_restaurants_endpoint():
    return load_restaurants()


@app.get("/reservations")
async def list_reservations():
    return reservations.get_all()