"""
Disiscrizione one-click da una campagna promozionale.

Il link arriva via email (nessun login richiesto): il token, generato con
django.core.signing.dumps, identifica campagna + contatto senza esporre gli
ID in chiaro e senza bisogno di un account per usarlo.
"""
import logging

from django.core import signing
from django.shortcuts import render
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

UNSUB_SALT = 'promo-campaign-optout'


@require_GET
def campaign_unsubscribe_view(request, token):
    """Disiscrive il contatto da UNA campagna specifica (non da tutte le
    comunicazioni). Idempotente: rivisitare il link non fa nulla di nuovo."""
    from events.models import PromotionalCampaign, PromotionalCampaignOptOut
    from sponsors.models import Contact

    esito = 'errore'
    campaign = None
    try:
        data = signing.loads(token, salt=UNSUB_SALT)
        campaign = PromotionalCampaign.objects.filter(
            pk=data.get('c')).select_related('event').first()
        contact = Contact.objects.filter(pk=data.get('k')).first()
        if campaign and contact:
            PromotionalCampaignOptOut.objects.get_or_create(
                campaign=campaign, contact=contact)
            esito = 'ok'
            logger.info(
                "Disiscrizione campagna %s per contatto %s", campaign.id, contact.id)
    except signing.BadSignature:
        esito = 'errore'
    except Exception:
        logger.exception("Errore disiscrizione campagna (token=%s)", token)
        esito = 'errore'

    return render(request, 'portal/campaign_unsubscribe.html', {
        'esito': esito,
        'campaign': campaign,
    })
