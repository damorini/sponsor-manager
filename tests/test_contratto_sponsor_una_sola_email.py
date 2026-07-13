"""Regressione: la conferma di un preventivo MAIN non-ECM deve produrre
UNA SOLA email col contratto (subito+Allegato1 uniti in un PDF), non due
email diverse (una delle quali con soggetto/testo obsoleto "Domanda di
ammissione confermata"). Copre anche l'eliminazione della generazione
duplicata/in race nel portale."""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from events.models import Event, EventType
from shared.models import Communication, Document
from sponsors.models import Contact, ContactRole


def _completa_anagrafica(sponsor):
    sponsor.sdi_code = 'ABCDEFG'
    sponsor.pec_email = 'pec@test.it'
    sponsor.address_street = 'Via Roma 1'
    sponsor.address_city = 'Bologna'
    sponsor.address_zip = '40100'
    sponsor.address_province = 'BO'
    sponsor.website = 'https://test.it'
    sponsor.business_description = 'Distributore'
    sponsor.save()


@pytest.fixture
def contratto_pronto(db, user_sponsor, sponsor):
    from django.utils import timezone
    from core.models import OrganizerSettings
    _completa_anagrafica(sponsor)
    Contact.objects.create(
        portal_user=user_sponsor, sponsor=sponsor,
        full_name='Mario Rossi', email='mario@test.it',
        roles=[ContactRole.OPERATIONAL], is_signer=True,
        privacy_accepted_at=timezone.now(),
        privacy_policy_version=OrganizerSettings.load().privacy_policy_version or '1.0',
    )
    event = Event.objects.create(
        name={'it': 'Evento Unico Email', 'en': 'Single Email Event'},
        code='UE', event_type=EventType.NON_ECM,
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event,
        contract_kind=ContractKind.MAIN, status=ContractStatus.SENT,
        contract_number='UE-26-001',
    )
    service = Service.objects.create(
        event=event, code='SRV1', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('100'), vat_rate=Decimal('22'),
    )
    ContractLine.objects.create(
        contract=contract, service=service, quantity=1,
        unit_price=Decimal('100'), vat_rate=Decimal('22'),
    )
    return contract


@pytest.mark.django_db
def test_una_sola_email_con_soggetto_corretto(client, user_sponsor, contratto_pronto):
    client.force_login(user_sponsor)
    resp = client.post(reverse('portal:quote_confirm', args=[contratto_pronto.id]))
    assert resp.status_code == 302

    ct = ContentType.objects.get_for_model(Contract)
    comms = Communication.objects.filter(
        content_type=ct, object_id=contratto_pronto.id,
        communication_type='initial_send',
    )
    assert comms.count() == 1, (
        f"attesa UNA sola email, trovate {comms.count()}: "
        f"{list(comms.values_list('subject', flat=True))}"
    )
    comm = comms.first()
    assert 'Contratto di sponsorizzazione' in comm.subject
    assert 'Domanda di ammissione confermata' not in comm.subject
    assert 'mario@test.it' in comm.recipients_to
    assert 'amministrazione@valet.it' in comm.recipients_cc
    assert 'morini@valet.it' in comm.recipients_cc


@pytest.mark.django_db
def test_documento_allegato_e_pdf_unico_con_allegato1(client, user_sponsor, contratto_pronto):
    client.force_login(user_sponsor)
    client.post(reverse('portal:quote_confirm', args=[contratto_pronto.id]))

    docs = Document.objects.filter(
        object_id=contratto_pronto.id, deleted_at__isnull=True,
        document_type='sponsor_contract',
    )
    assert docs.count() == 1, "atteso UN solo documento sponsor_contract vivo"
    doc = docs.first()
    assert doc.mime_type == 'application/pdf', f"atteso PDF, trovato {doc.mime_type}"
    assert 'completo' in doc.file_name, "il nome file deve indicare il PDF unito (contratto+Allegato1)"
