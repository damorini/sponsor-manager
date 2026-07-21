"""Regressione: quando viene generata la fattura proforma (azione admin
'Genera FATTURA PROFORMA'), il cliente riceve un'email che lo avvisa e lo
rimanda a "I miei documenti" nel portale."""
import pytest
from datetime import date
from decimal import Decimal

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services.pdf_generator import generate_proforma_pdf
from contracts.tasks.notifications import send_proforma_generated_notification
from events.models import Event
from shared.models import Communication, CommunicationType
from sponsors.models import Contact


@pytest.fixture
def contratto_con_referente(db, sponsor):
    Contact.objects.create(
        sponsor=sponsor, full_name='Referente Test', email='referente@test.it',
        roles=['operational'], is_primary=True,
    )
    event = Event.objects.create(
        name={'it': 'Ev Proforma Mail', 'en': 'Ev Proforma Mail'}, code='PFM',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PFM-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'),
    )


@pytest.mark.django_db
def test_notifica_inviata_dopo_generazione_proforma(contratto_con_referente):
    docs = generate_proforma_pdf(contratto_con_referente)
    send_proforma_generated_notification(contratto_con_referente.id, [d.id for d in docs])

    comm = Communication.objects.filter(
        object_id=contratto_con_referente.id,
        communication_type=CommunicationType.PROFORMA_GENERATED,
    ).first()
    assert comm is not None, "attesa una Communication di tipo proforma_generated"
    assert 'referente@test.it' in comm.recipients_to
    assert 'PFM-26-001' in comm.subject
    assert '/portal/contracts/' in comm.body_html or str(contratto_con_referente.id) in comm.body_html


@pytest.mark.django_db
def test_azione_admin_genera_proforma_invia_notifica(client, contratto_con_referente):
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    get_user_model().objects.create_superuser('op_admin', 'op_admin@test.it', 'x')
    client.login(username='op_admin@test.it', password='x')
    url = reverse('admin:contracts_contract_changelist')
    resp = client.post(url, {
        'action': 'action_genera_proforma',
        '_selected_action': [str(contratto_con_referente.id)],
    }, follow=True)
    assert resp.status_code == 200

    assert Communication.objects.filter(
        object_id=contratto_con_referente.id,
        communication_type=CommunicationType.PROFORMA_GENERATED,
    ).exists()


@pytest.mark.django_db
def test_nessun_destinatario_non_fallisce(db, sponsor):
    """Sponsor senza nessun contatto con ruolo signer/finance/operational:
    la notifica non deve sollevare eccezioni, solo loggare ed uscire."""
    event = Event.objects.create(
        name={'it': 'Ev Senza Referenti', 'en': 'Ev No Contacts'}, code='PFN',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    contratto = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='PFN-26-001',
        total=Decimal('1220.00'),
    )
    # non deve sollevare
    send_proforma_generated_notification(contratto.id, [])
