"""
Logique de transfert d'appel vers un humain.
Trois niveaux de déclenchement :
1. Mot-clé immédiat (allergie, gérant, urgence...) → sans passer par GPT
2. Question répétée 2 fois (filet de sécurité)
3. GPT répond TRANSFER (demande hors-scope ou info manquante)
"""

from app.config import TRANSFER_KEYWORDS


def needs_immediate_transfer(text: str) -> bool:
    """Détecte les mots-clés sensibles sans appeler GPT (coût zéro sur ces cas)."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in TRANSFER_KEYWORDS)


def is_transfer_response(gpt_reply: str) -> bool:
    """Vérifie si GPT a demandé un transfert."""
    return gpt_reply.strip().upper().startswith("TRANSFER")