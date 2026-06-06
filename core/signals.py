"""
Segnali di core.

Auto-traduzione: prima di salvare un modello traducibile (che dichiara
TRANSLATABLE_FIELDS), compila le traduzioni mancanti (es. inglese da italiano)
via DeepL. Vale per il salvataggio dall'admin E per gli import da Excel
(che usano get_or_create / save()).
"""
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save)
def autofill_translations_on_save(sender, instance, **kwargs):
    # Solo per i modelli traducibili (hanno TRANSLATABLE_FIELDS non vuoto).
    if not getattr(sender, 'TRANSLATABLE_FIELDS', None):
        return
    fn = getattr(instance, 'autofill_translations', None)
    if callable(fn):
        fn()


@receiver(pre_save)
def autofill_variant_label_en(sender, instance, **kwargs):
    """Varianti servizio: traduce 'label' (IT) -> 'label_en' (EN) se vuoto.

    Le varianti usano due CharField separati (label / label_en), non un JSON,
    quindi non rientrano in TRANSLATABLE_FIELDS: serve un handler dedicato.
    """
    if sender.__name__ not in ('ServiceVariant', 'CatalogServiceVariant'):
        return
    from django.conf import settings
    if not getattr(settings, 'AUTO_TRANSLATE_ON_SAVE', True):
        return
    label = (getattr(instance, 'label', '') or '').strip()
    label_en = (getattr(instance, 'label_en', '') or '').strip()
    if not label or label_en:
        return  # niente sorgente, oppure EN gia' compilato a mano
    try:
        from core.translation import translate_text
        instance.label_en = translate_text(label, source='it', target='en') or ''
    except Exception:
        pass
