"""
Gestion des données restaurant :
- Chargement depuis le fichier JSON
- Recherche par numéro de téléphone
- Formatage des données pour le prompt GPT
- Construction du prompt système
"""

import json
import logging
from app.config import RESTAURANTS_FILE, DEFAULT_RESTAURANT

logger = logging.getLogger("chatbot")


def load_restaurants() -> dict:
    with open(RESTAURANTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_restaurant_by_number(phone_number: str) -> dict:
    restaurants = load_restaurants()
    restaurant = restaurants.get(phone_number)
    if not restaurant:
        logger.warning(f"[WARNING] Numéro {phone_number!r} non trouvé → restaurant par défaut")
        return DEFAULT_RESTAURANT
    return restaurant


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
Ne termine jamais ta réponse par une question du type "Avez-vous d'autres questions ?".

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

2. La transcription vocale peut contenir de légères erreurs. Si tu devines la question, réponds-y directement.

3. Si la demande dépasse ce que tu peux gérer (événement privé, commande volumineuse, partenariat...),
   réponds UNIQUEMENT par le mot : TRANSFER

4. Si tu n'as vraiment pas l'information demandée, réponds UNIQUEMENT par le mot : TRANSFER

5. Ne dis jamais que tu es une IA sauf si on te le demande explicitement.
6. Ne parle jamais des outils ou technologies utilisés.
7. Ne termine jamais par "Avez-vous d'autres questions ?" ou toute formulation similaire.
"""