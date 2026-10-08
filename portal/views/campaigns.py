"""
Disiscrizione one-click da una campagna promozionale.

Il link arriva via email (nessun login richiesto): il token, generato con
django.core.signing.dumps, identifica campagna + contatto senza esporre gli
ID in chiaro e senza bisogno di un account per usarlo.
"""
import logging

from django.core import signing
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

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


@csrf_exempt   # niente sessione: la credenziale e' il token firmato nell'URL
@require_http_methods(['GET', 'POST'])
def marketing_unsubscribe_view(request, token):
    """Disiscrive l'INDIRIZZO da tutte le campagne promozionali (per area e
    per evento). Idempotente. Le email transazionali continuano.
    GET mostra solo il pulsante di conferma: filtri antispam e anteprime dei
    client di posta aprono i link da soli e non devono disiscrivere nessuno.
    La disiscrizione avviene col POST del pulsante."""
    from contracts.tasks.notifications import MARKETING_UNSUB_SALT
    from sponsors.models import SuppressedEmail

    esito = 'errore'
    try:
        email = (signing.loads(token, salt=MARKETING_UNSUB_SALT).get('e') or '').strip()
        if not email:
            esito = 'errore'
        elif request.method != 'POST':
            esito = 'conferma'
        elif SuppressedEmail.add(email, SuppressedEmail.Reason.UNSUBSCRIBED):
            esito = 'ok'
            logger.info("Disiscrizione marketing globale registrata")
    except signing.BadSignature:
        esito = 'errore'
    except Exception:
        # mai il token nel log: e' la credenziale per disiscrivere quell'indirizzo
        logger.exception("Errore disiscrizione marketing globale")
        esito = 'errore'
    return render(request, 'portal/campaign_unsubscribe.html', {
        'esito': esito, 'campaign': None, 'globale': True})
