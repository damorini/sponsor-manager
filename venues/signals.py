"""
Signal venues: alla creazione/modifica di uno Stand assicura che esista il
servizio "Spazio espositivo" della sua TIPOLOGIA per l'evento, cosi' e' subito
configurabile con gli inclusi (banner/desk/sedie...) senza aspettare la prima
vendita di uno stand. Idempotente.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Stand

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Stand)
def ensure_stand_service_for_type(sender, instance, created, raw=False, **kwargs):
    # 'raw' = caricamento da fixture (loaddata): non eseguire logica applicativa.
    if raw or not instance.event_id:
        return
    try:
        from contracts.services.stand_line import get_or_create_stand_service
        get_or_create_stand_service(instance.event, instance.stand_type or "")
    except Exception:
        logger.exception(
            "ensure_stand_service_for_type fallito per stand %s", instance.pk
        )
