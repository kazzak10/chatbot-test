"""
Configuration centrale : variables d'environnement et constantes.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Chemins ──────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
RESTAURANTS_FILE = DATA_DIR / "restaurants.json"
RESERVATIONS_FILE = DATA_DIR / "reservations.json"

# ─── Clés API ─────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")

# ─── Paramètres conversation ──────────────────────────────────────────────────
MAX_HISTORY_TURNS = 6  # Nombre max d'échanges gardés par appel (limite coût GPT)
GPT_MODEL = "gpt-4o-mini"
GPT_MAX_TOKENS = 150

# ─── Mots-clés transfert immédiat (sans passer par GPT) ─────────────────────
TRANSFER_KEYWORDS = [
    "allergie", "allergique", "urgence", "urgent",
    "plainte", "réclamation", "intoxication", "accident",
    "parler à quelqu'un", "parler à une personne", "gérant", "manager",
    "responsable", "je veux un humain",
]

# ─── Restaurant par défaut si numéro inconnu ─────────────────────────────────
DEFAULT_RESTAURANT = {
    "name": "notre restaurant",
    "hours": {},
    "address": {},
    "menu": {},
}