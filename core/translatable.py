"""
Mixin per campi multilingua basati su JSONField.

Pattern: invece di avere `name_it` e `name_en` come colonne separate, usiamo
un singolo JSONField `name = {"it": "...", "en": "..."}`. Questo mixin
fornisce il metodo helper `translated(field, language)` con fallback.

Uso:
    class Service(TranslatableMixin, TimeStampedModel):
        TRANSLATABLE_FIELDS = ['name', 'description']
        DEFAULT_LANGUAGE_FIELD = 'event__default_language'
        
        name = models.JSONField()
        description = models.JSONField(null=True, blank=True)
        ...

    service.translated('name', 'en')  # → "Workshop"
    service.translated('name')        # → versione italiana di default
"""


class TranslatableMixin:
    """
    Aggiunge supporto multilingua a un modello con JSONField come campi
    traducibili.
    
    Sottoclassi devono definire:
        TRANSLATABLE_FIELDS: lista di nomi di campi JSONField traducibili
    
    Opzionale:
        DEFAULT_LANGUAGE: lingua di fallback (default 'it')
    """
    TRANSLATABLE_FIELDS = []
    DEFAULT_LANGUAGE = 'it'

    def translated(self, field, language=None):
        """
        Restituisce il valore tradotto del campo.
        Fallback: lingua richiesta → default → 'it' → prima disponibile.
        """
        if field not in self.TRANSLATABLE_FIELDS:
            raise ValueError(
                f"{field} non è un campo traducibile. "
                f"Disponibili: {self.TRANSLATABLE_FIELDS}"
            )

        value = getattr(self, field, None) or {}
        if not isinstance(value, dict) or not value:
            return ''

        from django.utils.translation import get_language
        for lang in [language, get_language(), self.DEFAULT_LANGUAGE, 'it']:
            if lang and lang in value and value[lang]:
                return value[lang]

        return next(iter(value.values()), '')

    def set_translation(self, field, language, value):
        """Setter helper per aggiungere/aggiornare una singola traduzione."""
        if field not in self.TRANSLATABLE_FIELDS:
            raise ValueError(f"{field} non è un campo traducibile.")

        current = getattr(self, field) or {}
        if not isinstance(current, dict):
            current = {}
        current[language] = value
        setattr(self, field, current)

    def has_translation(self, field, language):
        """Verifica se esiste una traduzione per la lingua data."""
        value = getattr(self, field, None) or {}
        return isinstance(value, dict) and bool(value.get(language))

    def available_languages(self, field):
        """Lista delle lingue per cui esiste una traduzione del campo."""
        value = getattr(self, field, None) or {}
        if not isinstance(value, dict):
            return []
        return [lang for lang, val in value.items() if val]

    def autofill_translations(self, source='it', target='en'):
        """Compila automaticamente le traduzioni mancanti (es. EN da IT) via DeepL.

        - agisce solo dove c'è il testo sorgente e MANCA quello di destinazione
          (non sovrascrive mai una traduzione già inserita a mano);
        - non solleva eccezioni: se DeepL non è disponibile, lascia il campo
          vuoto e `translated()` fa il fallback sull'italiano.

        Viene richiamato automaticamente al salvataggio (vedi core/signals.py),
        così l'inglese si popola da solo anche negli import da Excel.
        """
        from django.conf import settings
        if not getattr(settings, 'AUTO_TRANSLATE_ON_SAVE', True):
            return
        try:
            from core.translation import translate_text
        except Exception:
            return

        for field in self.TRANSLATABLE_FIELDS:
            value = getattr(self, field, None)
            if not isinstance(value, dict):
                continue
            src_text = (value.get(source) or '').strip()
            has_target = bool((value.get(target) or '').strip())
            if not src_text or has_target:
                continue
            try:
                is_html = '<' in src_text and '>' in src_text
                translated = translate_text(src_text, source=source, target=target, html=is_html)
            except Exception:
                continue  # non bloccare il salvataggio
            if translated:
                value[target] = translated
                setattr(self, field, value)
