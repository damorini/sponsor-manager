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
