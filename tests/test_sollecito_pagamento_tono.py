"""Tono del SOLLECITO (scadenza superata) per una scadenza di PAGAMENTO:
deve essere accondiscendente ('scusiamo se torniamo a scrivervi', ipotesi
che il cliente abbia gia' pagato) invece che diretto/allarmante ('Attenzione',
riquadro rosso 'scaduta da N giorni'). Le scadenze NON di pagamento (materiali)
restano invece dirette, perche' bloccano davvero l'operativita'."""
from datetime import date, timedelta

import pytest
from decimal import Decimal
from django.core import mail
from django.utils import timezone


@pytest.fixture
def contratto_con_acconto_scaduto(db, sponsor):
    from sponsors.models import Contact, ContactRole
    from events.models import Event
    from contracts.models import Contract, ContractKind, ContractStatus, Deadline
    Contact.objects.create(
        sponsor=sponsor, full_name='Mario Pagatore', email='pagatore@test.it',
        roles=[ContactRole.OPERATIONAL], is_primary=True,
    )
    event = Event.objects.create(
        name={'it': 'Sollecito Ev', 'en': 'Sollecito Ev'}, code='SOL',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='SOL-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'),
        signed_date=date(2026, 6, 1),
    )
    deadline = Deadline.objects.create(
        contract=contract, deadline_type='pagamento_acconto',
        title='Scadenza acconto',
        due_date=timezone.now().date() - timedelta(days=5),
    )
    return contract, deadline


def _html(m):
    corpi = [m.body or '']
    for alt, _mime in getattr(m, 'alternatives', []):
        corpi.append(alt or '')
    return ' '.join(corpi)


@pytest.mark.django_db
def test_sollecito_pagamento_ha_tono_accondiscendente(contratto_con_acconto_scaduto):
    from contracts.tasks.notifications import send_deadline_reminder
    contract, deadline = contratto_con_acconto_scaduto
    mail.outbox.clear()
    send_deadline_reminder(deadline.id, reminder_type='overdue')

    assert len(mail.outbox) >= 1
    html = _html(mail.outbox[0])
    assert 'ci scusiamo se torniamo a scrivervi' in html.lower()
    assert 'è molto probabile che abbiate già provveduto' in html.lower()
    # NON deve avere il tono allarmante da sollecito materiali
    assert 'attenzione' not in html.lower()
    assert 'risulta scaduta da' not in html.lower()
    assert 'essenziale per la corretta gestione operativa' not in html.lower()
    assert '300,00' in html or '300.00' in html


@pytest.mark.django_db
def test_sollecito_materiali_resta_diretto(contratto_con_acconto_scaduto):
    """Le scadenze NON di pagamento (es. materiali) NON vanno addolcite:
    bloccano davvero l'operativita' dell'evento."""
    from contracts.models import Deadline
    from contracts.tasks.notifications import send_deadline_reminder
    contract, _ = contratto_con_acconto_scaduto
    tecnica = Deadline.objects.create(
        contract=contract, deadline_type='materiali',
        title='Invio logo HD',
        due_date=timezone.now().date() - timedelta(days=3),
    )
    mail.outbox.clear()
    send_deadline_reminder(tecnica.id, reminder_type='overdue')

    html = _html(mail.outbox[0])
    assert 'Attenzione' in html
    assert 'risulta scaduta da' in html
    assert 'Invio logo HD' in html
