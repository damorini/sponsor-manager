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
