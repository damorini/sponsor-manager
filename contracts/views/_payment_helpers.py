"""Shared helpers for checkout views."""
from decimal import Decimal


def compute_due_amount(contract):
    """Importo dovuto per il prossimo pagamento (acconto o saldo).

    Per contratti DRAFT/PENDING_PAYMENT restituisce il totale intero.
    Per SIGNED/ACTIVE: usa lo stato delle scadenze come sorgente di verità;
    fallback all'aritmetica sui Payment SUCCEEDED se le deadline non esistono.
    """
    from contracts.models import ContractStatus, DeadlineStatus
    from contracts.payments import Payment, PaymentStatus
    from django.db.models import Sum

    if contract.status not in [ContractStatus.SIGNED, ContractStatus.ACTIVE]:
        return contract.total or Decimal('0')

    def _paid():
        return (
            Payment.objects
            .filter(contract=contract, status=PaymentStatus.SUCCEEDED)
            .aggregate(s=Sum('amount_gross'))['s'] or Decimal('0')
        )

    if contract.has_deposit:
        acc_dl = contract.deadlines.filter(deadline_type='pagamento_acconto').first()
        if acc_dl:
            if acc_dl.status != DeadlineStatus.RECEIVED:
                return max(contract.deposit_amount - _paid(), Decimal('0'))
            # acconto già ricevuto → vai al saldo
        else:
            paid = _paid()
            if paid < contract.deposit_amount:
                return contract.deposit_amount - paid

    sal_dl = contract.deadlines.filter(deadline_type='pagamento_saldo').first()
    if sal_dl:
        if sal_dl.status != DeadlineStatus.RECEIVED:
            return max((contract.total or Decimal('0')) - _paid(), Decimal('0'))
        return Decimal('0')  # tutto pagato

    remaining = (contract.total or Decimal('0')) - _paid()
    return max(remaining, Decimal('0'))
