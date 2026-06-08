"""
Privacy nel portale:
- pagina informativa (consultabile sempre),
- pagina di presa visione/consensi al primo accesso (o quando cambia versione).
"""
from django.contrib import messages as flash
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from portal.views.dashboard import sponsor_required

# Testo segnaposto se l'informativa non è ancora stata inserita in admin.
INFORMATIVA_DEFAULT = (
    "Informativa privacy (segnaposto). Inserire il testo definitivo da "
    "«Impostazioni segreteria» nel backoffice.\n\n"
    "Titolare del trattamento: VALET S.r.l. I dati che fornisci (es. email, "
    "telefono, dati aziendali) e i messaggi inviati tramite il portale sono "
    "trattati per gestire il rapporto di sponsorizzazione (base giuridica: "
    "esecuzione del contratto e legittimo interesse). I dati sono conservati "
    "per il tempo necessario agli adempimenti contrattuali e di legge. Hai "
    "diritto di accesso, rettifica, cancellazione e opposizione scrivendo al "
    "titolare. Le comunicazioni di marketing avvengono solo previo tuo "
    "consenso facoltativo e revocabile."
)


def _versione_corrente():
    from core.models import OrganizerSettings
    return (OrganizerSettings.load().privacy_policy_version or '1.0')


def _testo_informativa():
    from core.models import OrganizerSettings
    return (OrganizerSettings.load().privacy_policy or '').strip() or INFORMATIVA_DEFAULT


@sponsor_required
def privacy_policy_view(request):
    """Mostra l'informativa privacy (consultabile in qualsiasi momento)."""
    return render(request, 'portal/legal/privacy_policy.html', {
        'testo': _testo_informativa(),
        'versione': _versione_corrente(),
    })


@sponsor_required
@require_http_methods(['GET', 'POST'])
def privacy_consent_view(request):
    """Presa visione dell'informativa + consenso marketing (facoltativo)."""
    contact = request.contact
    versione = _versione_corrente()

    if request.method == 'POST':
        if not request.POST.get('privacy'):
            flash.error(request, "Per proseguire devi prendere visione dell'informativa.")
        else:
            now = timezone.now()
            contact.privacy_accepted_at = now
            contact.privacy_policy_version = versione
            if request.POST.get('marketing'):
                contact.marketing_consent = True
                contact.marketing_consent_at = now
            else:
                contact.marketing_consent = False
                contact.marketing_consent_at = None
            contact.save(update_fields=[
                'privacy_accepted_at', 'privacy_policy_version',
                'marketing_consent', 'marketing_consent_at', 'updated_at',
            ])
            flash.success(request, "Grazie. Preferenze salvate.")
            return redirect('portal:dashboard')

    from core.models import OrganizerSettings
    descrizione_breve = OrganizerSettings.load().privacy_short(
        getattr(request, 'LANGUAGE_CODE', 'it'))

    return render(request, 'portal/legal/privacy_consent.html', {
        'testo': _testo_informativa(),
        'descrizione_breve': descrizione_breve,
        'versione': versione,
        'gia_accettata': bool(contact.privacy_accepted_at),
        'marketing_attuale': contact.marketing_consent,
    })
