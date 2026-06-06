"""
Portale: i documenti del contratto sono visibili al cliente SOLO se
is_visible_to_sponsor=True (i documenti interni non devono trapelare).
"""
import pytest
from datetime import date
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from events.models import Event
from contracts.models import Contract, ContractKind, ContractStatus
from shared.models import Document, DocumentType


@pytest.fixture
def contratto_firmato(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Doc Ev', 'en': 'Doc Ev'}, code='DOC',
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2),
    )
    return Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='DOC-26-001',
    )


def _doc(contract, title, visible, fname):
    cct = ContentType.objects.get_for_model(Contract)
    return Document.objects.create(
        content_type=cct, object_id=contract.id,
        document_type=DocumentType.INVOICE, title=title,
        is_visible_to_sponsor=visible,
        storage_url='/media/x/' + fname, file_name=fname,
    )


@pytest.mark.django_db
def test_documento_visibile_compare(client, user_sponsor, sponsor, contact, contratto_firmato):
    _doc(contratto_firmato, 'Fattura', True, 'fattura.pdf')
    client.force_login(user_sponsor)
    h = client.get(reverse('portal:contract_detail', args=[contratto_firmato.id])).content.decode()
    assert 'fattura.pdf' in h


@pytest.mark.django_db
def test_documento_interno_non_compare(client, user_sponsor, sponsor, contact, contratto_firmato):
    _doc(contratto_firmato, 'Nota interna', False, 'interno.pdf')
    client.force_login(user_sponsor)
    h = client.get(reverse('portal:contract_detail', args=[contratto_firmato.id])).content.decode()
    assert 'interno.pdf' not in h
