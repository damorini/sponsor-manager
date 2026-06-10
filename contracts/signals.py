"""Signal dell'app contracts."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='contracts.Payment')
def firma_contratto_su_incasso(sender, instance, created, **kwargs):
    """
    Quando un Payment diventa 'succeeded' su un contratto MAIN in draft/sent,
    firma automaticamente il contratto (qualsiasi incasso = impegno confermato).
    """
    from contracts.models import ContractStatus, ContractKind
    from contracts.payments import PaymentStatus

    payment = instance
    if payment.status != PaymentStatus.SUCCEEDED:
        return

    contract = payment.contract
    if contract is None:
        return
    if contract.contract_kind != ContractKind.MAIN:
        return
    if contract.status not in (ContractStatus.DRAFT, ContractStatus.SENT):
        return

    try:
        contract.mark_as_signed()
        logger.info(
            "Contratto %s firmato automaticamente per incasso (%s euro)",
            contract.contract_number, payment.amount_gross,
        )
    except Exception:
        logger.exception(
            "Impossibile firmare automaticamente il contratto %s dopo l'incasso",
            getattr(contract, 'contract_number', '?'),
        )


# ---------------------------------------------------------------------------
# Generazione scadenze "a prova di errore"
# ---------------------------------------------------------------------------
# Di base le scadenze si generano alla FIRMA (Contract.mark_as_signed).
# Questi signal coprono i casi in cui la configurazione cambia DOPO la firma,
# così l'operatore non deve ricordarsi dell'azione manuale:
#   - si aggiunge/modifica un Template scadenza su un servizio gia' venduto;
#   - si attiva la spunta "Genera scadenze" su un servizio gia' venduto;
#   - si aggiunge una riga servizio a un contratto gia' firmato.
# _generate_deadlines e' idempotente, quindi richiamarlo non crea duplicati.

def _stati_gia_firmati():
    from contracts.models import ContractStatus
    return (ContractStatus.SIGNED, ContractStatus.ACTIVE, ContractStatus.COMPLETED)


def _rigenera_scadenze(contract):
    """Richiama _generate_deadlines senza mai far fallire il salvataggio."""
    try:
        contract._generate_deadlines()
    except Exception:
        logger.exception(
            "Rigenerazione scadenze fallita per il contratto %s",
            getattr(contract, 'contract_number', '?'),
        )


def _rigenera_per_servizio(service):
    """Rigenera le scadenze su tutti i contratti GIA' FIRMATI che vendono
    questo servizio (catalog.Service per-evento)."""
    from contracts.models import Contract
    contracts = (Contract.objects
                 .filter(lines__service=service, status__in=_stati_gia_firmati())
                 .distinct())
    for contract in contracts:
        _rigenera_scadenze(contract)


@receiver(post_save, sender='contracts.ContractLine')
def genera_scadenze_su_nuova_riga(sender, instance, created, **kwargs):
    """Riga servizio aggiunta a un contratto gia' firmato -> genera le sue scadenze."""
    contract = instance.contract
    if contract and contract.status in _stati_gia_firmati():
        _rigenera_scadenze(contract)


@receiver(post_save, sender='catalog.DeadlineTemplate')
def genera_scadenze_su_template(sender, instance, **kwargs):
    """Template scadenza creato/modificato -> rigenera sui contratti firmati
    che vendono il servizio collegato."""
    service = getattr(instance, 'service', None)
    if service is not None:
        _rigenera_per_servizio(service)


@receiver(post_save, sender='catalog.Service')
def genera_scadenze_su_servizio(sender, instance, **kwargs):
    """Spunta 'Genera scadenze' (o altre modifiche) sul servizio -> rigenera
    sui contratti firmati che lo vendono."""
    if getattr(instance, 'triggers_deadlines', False):
        _rigenera_per_servizio(instance)
