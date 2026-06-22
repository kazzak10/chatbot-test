"""
Gestion de la mémoire conversationnelle par appel.
Stockage en RAM (dict) — suffisant pour la durée d'un appel.
Le CallSid Twilio est utilisé comme clé unique par appel.
"""

from app.config import MAX_HISTORY_TURNS

# { call_sid: [ {"role": "user"|"assistant", "content": "..."}, ... ] }
_sessions: dict[str, list[dict]] = {}


def get_history(call_sid: str) -> list[dict]:
    return _sessions.get(call_sid, [])


def add_message(call_sid: str, role: str, content: str) -> None:
    history = _sessions.setdefault(call_sid, [])
    history.append({"role": role, "content": content})
    # Limite la taille pour maîtriser les coûts GPT
    max_messages = MAX_HISTORY_TURNS * 2  # *2 car user + assistant par tour
    if len(history) > max_messages:
        _sessions[call_sid] = history[-max_messages:]


def clear(call_sid: str) -> None:
    _sessions.pop(call_sid, None)


def is_repeated(call_sid: str, user_text: str) -> bool:
    """Retourne True si l'utilisateur a déjà posé exactement la même question dans cet appel."""
    history = get_history(call_sid)
    user_messages = [m["content"].lower() for m in history if m["role"] == "user"]
    return user_messages.count(user_text.lower()) >= 2