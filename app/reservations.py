"""
Sauvegarde des réservations détectées pendant les appels.
Stockage simple en JSON local — à terme remplaçable par une BDD ou Google Calendar.
"""

import json
import logging
from datetime import datetime
from app.config import RESERVATIONS_FILE

logger = logging.getLogger("chatbot")


def save(call_sid: str, restaurant_name: str, confirmation_text: str) -> None:
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

    logger.info(f"[RESERVATION] Sauvegardée pour {restaurant_name} | CallSid={call_sid}")


def get_all() -> list:
    if RESERVATIONS_FILE.exists():
        with open(RESERVATIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []