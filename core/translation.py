# -*- coding: utf-8 -*-
# Traduzione automatica testi (IT->EN) via DeepL.
# Richiede DEEPL_API_KEY nel file .env. Chiave gratuita: https://www.deepl.com/pro-api
from django.conf import settings


class TranslationError(Exception):
    pass


def translate_text(text, source='it', target='en'):
    key = (getattr(settings, 'DEEPL_API_KEY', '') or '').strip()
    if not key:
        raise TranslationError(
            "Traduzione non configurata: imposta DEEPL_API_KEY nel file .env "
            "(chiave gratuita su deepl.com/pro-api)."
        )
    import requests
    base = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    try:
        resp = requests.post(
            base + "/v2/translate",
            headers={"Authorization": "DeepL-Auth-Key " + key},
            data={
                "text": text,
                "source_lang": source.upper(),
                "target_lang": target.upper(),
            },
            timeout=15,
        )
    except Exception:
        raise TranslationError("Impossibile contattare il servizio di traduzione.")
    if resp.status_code == 403:
        raise TranslationError("Chiave DeepL non valida o non autorizzata.")
    if resp.status_code == 456:
        raise TranslationError("Quota di traduzione DeepL esaurita per questo mese.")
    if resp.status_code != 200:
        raise TranslationError("Servizio di traduzione: errore %s." % resp.status_code)
    data = resp.json()
    translations = data.get("translations") or []
    if not translations:
        raise TranslationError("Nessuna traduzione ricevuta.")
    return translations[0].get("text", "")
