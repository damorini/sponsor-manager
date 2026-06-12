"""Shared helpers for checkout views."""
from decimal import Decimal


def compute_due_amount(contract):
    """Importo dovuto per il prossimo pagamento (acconto o saldo).

    Per contratti DRAFT/PENDING_PAYMENT restituisce il totale intero.
    Per SIGNED/ACTIVE calcola la quota ancora da versare:
      - acconto, se previsto e non ancora coperto dai pagamenti SUCCEEDED;
      - saldo (totale - già_pagato) altrimenti.
    """
    from contracts.models import ContractStatus
    from contracts.payments import Payment, PaymentStatus
    from django.db.models import Sum

    if contract.status not in [ContractStatus.SIGNED, ContractStatus.ACTIVE]:
        return contract.total or Decimal('0')

    total_paid = (
        Payment.objects
        .filter(contract=contract, status=PaymentStatus.SUCCEEDED)
        .aggregate(s=Sum('amount_gross'))['s'] or Decimal('0')
    )

    if contract.has_deposit and total_paid < contract.deposit_amount:
        return contract.deposit_amount - total_paid

    remaining = (contract.total or Decimal('0')) - total_paid
    return max(remaining, Decimal('0'))
