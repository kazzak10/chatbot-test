# 🎙️ Chatbot Vocal Restaurant

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?style=flat&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat&logo=docker&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?style=flat&logo=openai&logoColor=white)
![Twilio](https://img.shields.io/badge/Twilio-Voice-F22F46?style=flat&logo=twilio&logoColor=white)

Assistant téléphonique vocal pour restaurants, basé sur **Twilio Voice** et **GPT-4o-mini**. Il répond aux appels entrants, renseigne les clients (menu, horaires, allergènes...), prend des réservations et transfère automatiquement vers un humain en cas de besoin (urgence, demande hors-scope, incompréhension).

Le tout est multi-restaurant : chaque numéro Twilio est associé à une fiche restaurant distincte, avec sa propre carte, ses horaires et son ton.

## Stack technique

- **Python 3.12** + **FastAPI** — serveur webhook asynchrone
- **Twilio Voice / TwiML** — réception d'appels, reconnaissance vocale (Gather speech), transfert d'appel (Dial)
- **OpenAI GPT-4o-mini** — moteur conversationnel
- **Google Cloud Text-to-Speech** — synthèse vocale (voix `fr-FR-Wavenet-C`), avec repli automatique sur **Twilio Polly** en cas d'échec
- **Docker / Docker Compose** — conteneurisation et déploiement
- **httpx** — appels HTTP asynchrones vers Google TTS
- Stockage **JSON** local pour les fiches restaurants et les réservations

## Architecture

Flux d'un appel entrant, de la sonnerie jusqu'à la réponse vocale :

```
Appel entrant (client)
      │
      ▼
Twilio Voice ──POST /voice──▶ FastAPI
      │                          │
      │                    Identifie le restaurant via le numéro appelé (To)
      │                    Réinitialise la mémoire de l'appel (CallSid)
      │                          │
      │◀── TwiML (message d'accueil + <Gather>) ──┘
      │
Client parle
      │
      ▼
Twilio transcrit (Speech-to-Text) ──POST /process──▶ FastAPI
                                          │
                          ┌───────────────┼────────────────────┐
                          ▼               ▼                    ▼
                  Transcription      Mot-clé transfert    Question répétée /
                  vide (relance      immédiat (allergie,  transfert en attente
                  ou raccroche)      urgence, gérant...)  confirmé par le client
                          │               │                    │
                          └───────────────┴─────────┬──────────┘
                                                      ▼
                                          Sinon → appel GPT-4o-mini
                                          (prompt système = fiche restaurant
                                          + règles métier + historique)
                                                      │
                                          Réponse GPT normale, demande de
                                          transfert (TRANSFER), ou confirmation
                                          de réservation (→ sauvegarde JSON)
                                                      │
                                                      ▼
                                   Texte de la réponse envoyé à Google TTS
                                   (POST /audio/{CallSid} généré et mis en cache)
                                                      │
                                                      ▼
                              TwiML renvoyé à Twilio (<Play> l'audio généré,
                              ou <Say> Polly si Google TTS indisponible)
                                                      │
                                                      ▼
                                         Le client entend la réponse,
                                    et un nouveau <Gather> attend sa réponse
```

En cas de transfert, Twilio compose le numéro du gérant (`<Dial>`) et notifie la fin de l'appel via `/transfer-complete`.

## Prérequis

- Python 3.12+
- Un compte [Twilio](https://www.twilio.com/) avec un numéro vocal configuré
- Une clé API [OpenAI](https://platform.openai.com/) (GPT-4o-mini)
- Une clé API [Google Cloud Text-to-Speech](https://cloud.google.com/text-to-speech) (optionnelle — sinon repli automatique sur Twilio Polly)
- Docker et Docker Compose (pour un lancement conteneurisé)
- [ngrok](https://ngrok.com/) ou équivalent pour exposer le serveur local à Twilio en développement

## Installation

```bash
git clone <url-du-repo>
cd chatbot_vocale_test

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Configuration

| Variable              | Description                                                        | Requis                             |
| --------------------- | ------------------------------------------------------------------ | ---------------------------------- |
| `OPENAI_API_KEY`      | Clé API OpenAI utilisée pour les réponses GPT-4o-mini              | Oui                                |
| `GOOGLE_TTS_API_KEY`  | Clé API Google Cloud Text-to-Speech pour la voix naturelle         | Non (repli sur Polly si absente)   |
| `DEBUG_TOKEN`         | Jeton secret pour protéger l'endpoint de debug `GET /restaurants`  | Non (endpoint désactivé si absent) |
| `TWILIO_ACCOUNT_SID`  | Identifiant du compte Twilio (configuration du numéro côté Twilio) | Oui (côté Twilio)                  |
| `TWILIO_AUTH_TOKEN`   | Jeton d'authentification Twilio                                    | Oui (côté Twilio)                  |
| `TWILIO_PHONE_NUMBER` | Numéro Twilio associé au webhook `/voice`                          | Oui (côté Twilio)                  |

Les fiches restaurants (adresse, horaires, menu, allergènes, numéro du gérant...) se configurent dans `app/data/restaurants.json`, indexées par numéro de téléphone appelé.

## Lancer le projet

### Avec Docker

```bash
docker-compose up --build
```

Le serveur est exposé sur `http://localhost:8000`.

### Sans Docker

```bash
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Puis exposer le port avec ngrok (`ngrok http 8000`) et configurer l'URL publique `https://.../voice` comme webhook vocal du numéro Twilio.

## Structure du projet

```
chatbot_vocale_test/
├── app/
│   ├── main.py            # Routes FastAPI : /voice, /process, /audio, /transfer-complete...
│   ├── config.py           # Variables d'environnement, constantes, mots-clés de transfert
│   ├── restaurant.py       # Chargement des fiches restaurant + construction du prompt système GPT
│   ├── memory.py           # Historique conversationnel par appel (RAM, clé = CallSid)
│   ├── transfer.py         # Logique de détection des transferts vers un humain
│   ├── twiml.py            # Génération des réponses TwiML (Gather, Dial, Say, Play, Hangup)
│   ├── voice.py            # Synthèse vocale via Google TTS + cache audio en RAM
│   └── data/
│       ├── restaurants.json    # Fiches restaurants (menu, horaires, ton, contact gérant...)
│       └── reservations.json   # Réservations confirmées, sauvegardées automatiquement
├── Dockerfile              # Image Python 3.12 slim + uvicorn
├── docker-compose.yml       # Service unique, port 8000, montage du dossier data
└── requirements.txt         # Dépendances Python
```

## Fonctionnalités

- **Réponses multi-restaurants** — un numéro Twilio par restaurant, chacun avec sa propre carte, ses horaires et son ton
- **Renseignements** — menu complet, allergènes, horaires, adresse, moyens de paiement, accessibilité, parking, promotions...
- **Prise de réservation** — collecte progressive (date, heure, nombre de personnes) puis confirmation et sauvegarde automatique
- **Prise de commande** — sur place, à emporter ou en livraison, avec collecte des informations une par une et récapitulatif final
- **Upselling naturel** — suggestion contextuelle après chaque commande ou réservation
- **Transfert vers un humain** à trois niveaux :
  - immédiat sur mot-clé sensible (allergie, urgence, réclamation...)
  - après une question répétée sans réponse satisfaisante
  - sur demande explicite de GPT (question hors-scope ou information manquante)
- **Gestion des silences** — relance en cas de transcription vide, raccroché propre après 3 échecs
- **Synthèse vocale naturelle** via Google TTS, avec repli automatique sur Twilio Polly en cas d'indisponibilité
- **Sécurité du prompt** — le bot ne change jamais de rôle, ne révèle jamais la configuration technique ni la liste des autres restaurants gérés

## Auteur

**Zakaria Houari**
