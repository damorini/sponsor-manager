"""Un carrello (CartSession) di un contratto cestinato non deve restare
candidato ai reminder di recupero carrello abbandonato.

Ieri sera check_abandoned_carts ha mandato 5 email 'hai lasciato servizi
nel carrello' per contratti ADDON di test gia' nel cestino: il carrello
era ACTIVE e non c'era nessun filtro sul contratto cestinato.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from tests.test_quote_confirm import _completa_anagrafica  # noqa: F401


@pytest.fixture
def carrello_con_riga(db, sponsor, user_sponsor):
    from sponsors.models import Contact, ContactRole
    from events.models import Event
    from catalog.models import Service
    from contracts.models import Contract, ContractKind, ContractStatus, ContractLine
    from contracts.payments import CartSession, CartSessionStatus

    _completa_anagrafica(sponsor)
    contact = Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor, full_name='Mario Rossi',
        email='mario@test.it', roles=[ContactRole.OPERATIONAL], is_signer=True,
    )
    event = Event.objects.create(
        name={'it': 'Cart Ev', 'en': 'Cart Ev'}, code='CRT',
        start_date=date(2026, 12, 5), end_date=date(2026, 12, 6),
    )
    service = Service.objects.create(
        event=event, code='CRT-SVC', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('50.00'), is_self_purchasable=True,
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT, contract_number='CRT-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    old = timezone.now() - timedelta(hours=48)
    cart = CartSession.objects.create(
        contract=contract, contact=contact, status=CartSessionStatus.ACTIVE,
        last_activity_at=old,
    )
    return contract, cart


@pytest.mark.django_db
def test_cestinare_il_contratto_chiude_il_carrello(carrello_con_riga):
    from contracts.payments import CartSessionStatus
    contract, cart = carrello_con_riga
    contract.delete()  # soft
    cart.refresh_from_db()
    assert cart.status == CartSessionStatus.EXPIRED


@pytest.mark.django_db
def test_check_abandoned_carts_ignora_contratti_cestinati(carrello_con_riga):
    from django.core import mail
    from contracts.tasks.scheduled import check_abandoned_carts
    contract, cart = carrello_con_riga
    contract.delete()
    # simula il dato storico: il carrello torna ACTIVE nonostante il cestino
    from contracts.payments import CartSession, CartSessionStatus
    CartSession.objects.filter(pk=cart.pk).update(status=CartSessionStatus.ACTIVE)

    mail.outbox.clear()
    n = check_abandoned_carts()
    assert n == 0
    assert mail.outbox == [], \
        "nessuna email di recupero carrello per un contratto cestinato"
