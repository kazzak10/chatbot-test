"""
Script de test rapide pour vérifier que Google TTS fonctionne.
Lance depuis la racine du projet : python3 test_google_tts.py
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_google_tts():
    api_key = os.getenv("GOOGLE_TTS_API_KEY", "")
    
    print("=" * 50)
    print("TEST GOOGLE TTS")
    print("=" * 50)
    
    # Test 1 : clé présente
    if not api_key:
        print("❌ GOOGLE_TTS_API_KEY manquante dans .env")
        sys.exit(1)
    print(f"✅ Clé API trouvée : {api_key[:8]}...")

    # Test 2 : appel API
    print("\n→ Appel Google TTS en cours...")
    import httpx
    try:
        payload = {
            "input": {"text": "Bonjour, bienvenue chez Le Petit Bistrot. Comment puis-je vous aider ?"},
            "voice": {
                "languageCode": "fr-FR",
                "name": "fr-FR-Wavenet-C",
                "ssmlGender": "FEMALE",
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": 1.0,
                "pitch": 0.0,
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://texttospeech.googleapis.com/v1/text:synthesize",
                json=payload,
                params={"key": api_key},
            )
            response.raise_for_status()
            audio = response.json().get("audioContent", "")
            if audio:
                print(f"✅ Audio généré avec succès ({len(audio)} caractères base64)")
                # Sauvegarde le fichier MP3 pour écoute
                import base64
                with open("test_output.mp3", "wb") as f:
                    f.write(base64.b64decode(audio))
                print("✅ Fichier test_output.mp3 créé — ouvre-le pour écouter la voix")
            else:
                print("❌ Réponse vide de Google TTS")

    except httpx.HTTPStatusError as e:
        print(f"❌ Erreur HTTP {e.response.status_code} : {e.response.text}")
    except Exception as e:
        print(f"❌ Erreur : {e}")

    print("\n" + "=" * 50)

asyncio.run(test_google_tts())