"""Promemoria scadenza di PAGAMENTO: versione curata dell'email.

Per le scadenze di pagamento il reminder mostra il riquadro riepilogo
(Acconto/Saldo, importo, data), i dati del bonifico con causale (solo se
configurati davvero: mai i placeholder "DA CONFIGURARE"), la frase sul
pagamento che si incrocia con la comunicazione e la chiusura di cortesia.
Le scadenze non di pagamento mantengono il promemoria classico.
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core import mail
from django.utils import timezone


@pytest.fixture
def contratto_con_acconto(db, sponsor):
    from sponsors.models import Contact, ContactRole
    from events.models import Event
    from contracts.models import Contract, ContractKind, ContractStatus, Deadline
    Contact.objects.create(
        sponsor=sponsor, full_name='Mario Pagatore', email='pagatore@test.it',
        roles=[ContactRole.OPERATIONAL], is_primary=True,
    )
    event = Event.objects.create(
        name={'it': 'Pay Rem Ev', 'en': 'Pay Rem Ev'}, code='PRE',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PRE-26-001',
        total=Decimal('1000.00'), deposit_percent=Decimal('30'),
        signed_date=date(2026, 7, 1),
    )
    deadline = Deadline.objects.create(
        contract=contract, deadline_type='pagamento_acconto',
        title='Scadenza acconto',
        due_date=timezone.now().date() + timedelta(days=7),
    )
    return contract, deadline


def _html(m):
    corpi = [m.body or '']
    for alt, _mime in getattr(m, 'alternatives', []):
        corpi.append(alt or '')
    return ' '.join(corpi)


@pytest.mark.django_db
def test_reminder_pagamento_con_bonifico(contratto_con_acconto, settings):
    from contracts.tasks.notifications import send_deadline_reminder
    settings.BANK_TRANSFER_HOLDER = 'Valet S.r.l.'
    settings.BANK_TRANSFER_BANK = 'Banca di Bologna'
    settings.BANK_TRANSFER_IBAN = 'IT60X0542811101000000123456'
    settings.BANK_TRANSFER_BIC = 'BDBOIT21'

    contract, deadline = contratto_con_acconto
    mail.outbox.clear()
    send_deadline_reminder(deadline.id, reminder_type='reminder')

    assert len(mail.outbox) >= 1
    html = _html(mail.outbox[0])
    assert 'promemoria di pagamento' in html.lower()
    assert 'Acconto' in html
    assert '300,00' in html or '300.00' in html   # 30% di 1000 (locale IT)
    assert 'IT60X0542811101000000123456' in html
    assert 'Causale' in html and 'PRE-26-001' in html
    assert 'dovesse incrociarsi con la presente' in html
    assert 'Ringraziando per la collaborazione' in html
    assert 'pagamenti/' in html        # CTA verso la pagina Pagamenti


@pytest.mark.django_db
def test_reminder_pagamento_senza_bonifico_configurato(contratto_con_acconto, settings):
    """Coi placeholder 'DA CONFIGURARE' il riquadro bonifico NON compare."""
    from contracts.tasks.notifications import send_deadline_reminder
    settings.BANK_TRANSFER_HOLDER = 'Valet S.r.l. (DA CONFIGURARE)'
    settings.BANK_TRANSFER_IBAN = 'IT00X0000000000000000000000'

    contract, deadline = contratto_con_acconto
    mail.outbox.clear()
    send_deadline_reminder(deadline.id, reminder_type='reminder')

    html = _html(mail.outbox[0])
    assert 'CONFIGURARE' not in html
    assert 'IBAN' not in html
    # il resto del promemoria resta integro
    assert 'Acconto' in html
    assert '300,00' in html or '300.00' in html


@pytest.mark.django_db
def test_reminder_non_pagamento_resta_classico(contratto_con_acconto):
    from contracts.models import Deadline
    from contracts.tasks.notifications import send_deadline_reminder
    contract, _ = contratto_con_acconto
    tecnica = Deadline.objects.create(
        contract=contract, deadline_type='materiali',
        title='Invio logo HD',
        due_date=timezone.now().date() + timedelta(days=10),
    )
    mail.outbox.clear()
    send_deadline_reminder(tecnica.id, reminder_type='reminder')

    html = _html(mail.outbox[0])
    assert 'Promemoria scadenza' in html
    assert 'Invio logo HD' in html
    assert 'incrociarsi' not in html
    assert 'Ringraziando per la collaborazione' in html
