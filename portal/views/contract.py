"""
View per il dettaglio di un singolo contratto del portale sponsor.

Mostra:
- Riepilogo contratto (numero, evento, stand, totali)
- Righe contratto (servizi acquistati con prezzi)
- Stato pagamento + bottoni paga (se pagabile)
- Storico pagamenti
- Lista scadenze operative (con stato, materiali caricati, ecc.)
- Documenti allegati (PDF contratto, ecc.)
"""
import logging
from datetime import date

from django.http import HttpResponseForbidden, Http404
from django.shortcuts import render, get_object_or_404

from portal.views.dashboard import sponsor_required

logger = logging.getLogger(__name__)


@sponsor_required
def contract_detail_view(request, contract_id):
    """
    Dettaglio contratto.
    
    Verifica che il contratto appartenga allo sponsor dell'utente loggato.
    """
    from contracts.models import Contract, ContractStatus, DeadlineStatus
    from contracts.payments import Payment, PaymentStatus
    from shared.models import Document, Communication
    from django.contrib.contenttypes.models import ContentType

    contract = get_object_or_404(
        Contract.objects.select_related(
            'event', 'sponsor', 'stand', 'stand_block',
            'parent_contract',
        ).prefetch_related('lines__service'),
        id=contract_id,
        deleted_at__isnull=True,
    )

    # Verifica accesso: solo se appartiene allo sponsor dell'utente
    if contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden(
            "Non hai accesso a questo contratto."
        )

    # Una bozza non e' ancora visibile al cliente nel portale.
    if contract.status == ContractStatus.DRAFT:
        return HttpResponseForbidden("Contratto non disponibile.")
    # Un contratto annullato non e' consultabile dal cliente nel portale.
    if contract.status == ContractStatus.CANCELLED:
        return HttpResponseForbidden("Questo contratto è stato annullato.")

    # Scadenze operative (is_overdue e days_remaining sono property del modello)
    deadlines = contract.deadlines.select_related('deadline_template').order_by('due_date')

    # Storico pagamenti
    payments = contract.payments.exclude(
        status=PaymentStatus.PENDING
    ).order_by('-initiated_at')

    # Eventuali payment pending (per evitare doppioni quando si clicca "Paga")
    pending_payment = contract.payments.filter(
        status=PaymentStatus.PENDING
    ).first()

    # Documenti allegati al contratto (PDF firmato, ecc.)
    contract_ct = ContentType.objects.get_for_model(Contract)
    documents = Document.objects.filter(
        content_type=contract_ct,
        object_id=contract.id,
        deleted_at__isnull=True,
    ).order_by('-created_at')

    # Comunicazioni inviate per il contratto
    communications = Communication.objects.filter(
        content_type=contract_ct,
        object_id=contract.id,
    ).order_by('-created_at')[:10]

    # Determina se il contratto è pagabile e quali bottoni mostrare
    is_payable = contract.status in [
        ContractStatus.DRAFT,
        ContractStatus.SENT,
        ContractStatus.PENDING_PAYMENT,
    ]

    # Servizi acquistabili per questo evento (per CTA "Aggiungi servizi")
    from catalog.models import Service
    purchasable_services_count = Service.objects.filter(
        event=contract.event,
        is_active=True,
        is_self_purchasable=True,
    ).count()

    return render(request, 'portal/contract/detail.html', {
        'contract': contract,
        'deadlines': deadlines,
        'payments': payments,
        'pending_payment': pending_payment,
        'documents': documents,
        'communications': communications,
        'is_payable': is_payable,
        'purchasable_services_count': purchasable_services_count,
    })
