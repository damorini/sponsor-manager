"""
#1 Dashboard pagamenti: una card per ogni scadenza di pagamento dello sponsor,
con importo + data + badge separati Firmato/Pagato.

build_payment_items(sponsor, today) -> (items, totale_da_pagare):
- una voce per scadenza di tipo 'pagament*' dei contratti non bozza/annullati
  ed eventi non archiviati;
- importo: acconto -> deposit_amount, saldo -> balance_amount, altrimenti total;
- firmato: contratto in Firmato/Attivo/Completato;
- pagato: scadenza RECEIVED; il totale somma solo le scadenze aperte.
"""
import pytest
from decimal import Decimal
from datetime import date

from portal.views.dashboard import build_payment_items


@pytest.mark.django_db
def test_payment_items_amounts_and_badges(sponsor):
    from events.models import Event
    from contracts.models import (
        Contract, ContractStatus, ContractKind, Deadline, DeadlineStatus)

    event = Event.objects.create(
        name={'it': 'Pay Ev', 'en': 'Pay Ev'}, code='PAY',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PAY-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'),
        signed_date=date(2026, 6, 1),
    )
    today = date(2026, 6, 10)
    # acconto NON pagato e gia' scaduto
    Deadline.objects.create(
        contract=contract, deadline_type='pagamento_acconto',
        title='Scadenza acconto', due_date=date(2026, 6, 5),
        status=DeadlineStatus.PENDING)
    # saldo PAGATO (ricevuto)
    Deadline.objects.create(
        contract=contract, deadline_type='pagamento_saldo',
        title='Scadenza saldo', due_date=date(2026, 9, 15),
        status=DeadlineStatus.RECEIVED)

    items, totale = build_payment_items(sponsor, today)

    assert len(items) == 2
    by_title = {it['title']: it for it in items}
    acc = by_title['Acconto da pagare']
    sal = by_title['Saldo da pagare']

    assert acc['amount'] == Decimal('300.00')
    assert acc['firmato'] is True
    assert acc['pagato'] is False
    assert acc['overdue'] is True

    assert sal['amount'] == Decimal('700.00')
    assert sal['firmato'] is True
    assert sal['pagato'] is True
    assert sal['overdue'] is False

    # nel totale entra solo la scadenza aperta (l'acconto)
    assert totale == Decimal('300.00')
    # le aperte vengono prima delle pagate
    assert items[0]['title'] == 'Acconto da pagare'


@pytest.mark.django_db
def test_payment_items_excludes_non_payment_and_cancelled(sponsor):
    from events.models import Event
    from contracts.models import (
        Contract, ContractStatus, ContractKind, Deadline, DeadlineStatus)

    event = Event.objects.create(
        name={'it': 'Pay Ev2', 'en': 'Pay Ev2'}, code='PAY2',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2),
    )
    # contratto ANNULLATO: le sue scadenze non compaiono
    c_cancel = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.CANCELLED, contract_number='PAY2-26-001',
        total=Decimal('500.00'), deposit_percent=Decimal('50'))
    Deadline.objects.create(
        contract=c_cancel, deadline_type='pagamento_acconto',
        title='Acconto', due_date=date(2026, 6, 5),
        status=DeadlineStatus.PENDING)
    # contratto valido con scadenza TECNICA (non pagamento): esclusa
    c_ok = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PAY2-26-002',
        total=Decimal('500.00'), deposit_percent=Decimal('0'))
    Deadline.objects.create(
        contract=c_ok, deadline_type='consegna_materiali',
        title='Materiali', due_date=date(2026, 7, 1),
        status=DeadlineStatus.PENDING)

    items, totale = build_payment_items(sponsor, date(2026, 6, 10))
    assert items == []
    assert totale == Decimal('0.00')


@pytest.mark.django_db
def test_payments_view_renders(client):
    """La pagina /portal/pagamenti/ risponde 200 e mostra una card pagamento
    con titolo, badge Firmato e Da pagare (e2e view+template+url+decorator)."""
    from django.urls import reverse
    from django.utils import timezone
    from django.contrib.auth import get_user_model
    from core.models import OrganizerSettings
    from sponsors.models import Sponsor, Contact, ContactRole
    from users.models import UserRole
    from events.models import Event
    from contracts.models import (
        Contract, ContractStatus, ContractKind, Deadline, DeadlineStatus)

    User = get_user_model()
    user = User.objects.create_user(
        username='pay_sp', email='pay@test.it', password='x', is_active=True)
    user.role = UserRole.SPONSOR
    user.save()
    # Anagrafica COMPLETA: altrimenti il decorator reindirizza a 'profilo'.
    sponsor = Sponsor.objects.create(
        legal_name='Pay Sponsor S.r.l.', vat_number='12345678901',
        sdi_code='ABCDEFG', pec_email='pec@pec.it', address_street='Via Test 1',
        address_city='Bologna', address_zip='40100', address_province='BO',
        address_country='IT', website='https://x.it', business_description='Test',
    )
    ver = OrganizerSettings.load().privacy_policy_version or '1.0'
    Contact.objects.create(
        portal_user=user, sponsor=sponsor, full_name='Pay Contact',
        email='c@test.it', phone='+390000', roles=[ContactRole.OPERATIONAL],
        privacy_accepted_at=timezone.now(), privacy_policy_version=ver)
    event = Event.objects.create(
        name={'it': 'E', 'en': 'E'}, code='E1',
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='E1-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'))
    Deadline.objects.create(
        contract=contract, deadline_type='pagamento_acconto',
        title='Scadenza acconto', due_date=date(2026, 9, 1),
        status=DeadlineStatus.PENDING)

    client.force_login(user)
    resp = client.get(reverse('portal:payments'))

    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Acconto da pagare' in html
    assert 'Totale da pagare' in html
    assert 'Firmato' in html
    assert 'Da pagare' in html
