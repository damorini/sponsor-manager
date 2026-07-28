"""Regressione: dal portale il cliente puo' di nuovo caricare la contabile
del bonifico sulle scadenze di PAGAMENTO (acconto/saldo) - funzione nascosta
per errore dal restyling del 29/5. A differenza dei materiali normali, il
caricamento NON marca la scadenza "Pagato": avvisa la segreteria, che
verifica l'accredito e registra l'incasso dal cruscotto."""
import io

import pytest
from datetime import date
from decimal import Decimal
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus, Deadline, DeadlineStatus
from events.models import Event
from portal.views.materials import _get_materials_for_contract
from shared.models import Communication, Document


@pytest.fixture
def contratto_con_saldo(db, user_sponsor, sponsor, contact):
    event = Event.objects.create(
        name={'it': 'Ev Contabile', 'en': 'Ev Contabile'}, code='CNT',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='CNT-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'), total=Decimal('1220.00'),
    )
    saldo = Deadline.objects.create(
        contract=contract, deadline_type='pagamento_saldo',
        title='Scadenza saldo', due_date=date(2026, 11, 1),
        status=DeadlineStatus.PENDING,
    )
    materiale = Deadline.objects.create(
        contract=contract, deadline_type='tecnica',
        title='Invio logo', due_date=date(2026, 10, 1),
        status=DeadlineStatus.PENDING,
    )
    return contract, saldo, materiale


def _pdf_finto(nome='contabile.pdf'):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(nome, b'%PDF-1.4 finto', content_type='application/pdf')


@pytest.mark.django_db
def test_scadenza_pagamento_ha_area_upload(contratto_con_saldo):
    contract, saldo, _ = contratto_con_saldo
    materials = _get_materials_for_contract(contract)
    m_saldo = next(m for m in materials if m['deadline'].id == saldo.id)
    assert m_saldo['is_payment'] is True
    assert m_saldo['needs_file'] is True, \
        "la scadenza di pagamento deve tornare ad avere l'area di upload (contabile bonifico)"


@pytest.mark.django_db
def test_upload_contabile_non_marca_pagato_e_avvisa_segreteria(
        client, user_sponsor, contratto_con_saldo):
    contract, saldo, _ = contratto_con_saldo
    client.force_login(user_sponsor)

    resp = client.post(
        reverse('portal:material_upload', args=[saldo.id]),
        {'files': _pdf_finto()},
    )
    assert resp.status_code == 302

    saldo.refresh_from_db()
    assert saldo.status == DeadlineStatus.PENDING, \
        "caricare la contabile NON deve marcare la scadenza come Pagato"

    from django.contrib.contenttypes.models import ContentType
    dl_ct = ContentType.objects.get_for_model(Deadline)
    assert Document.objects.filter(
        content_type=dl_ct, object_id=saldo.id, deleted_at__isnull=True).exists()

    # email di avviso alla segreteria (Celery EAGER in dev/test)
    comm = Communication.objects.filter(
        object_id=contract.id, subject__icontains='Contabile bonifico').first()
    assert comm is not None, "attesa email di avviso alla segreteria"
    assert 'amministrazione@valet.it' in comm.recipients_to


@pytest.mark.django_db
def test_upload_materiale_normale_marca_ancora_ricevuto(
        client, user_sponsor, contratto_con_saldo):
    """Regressione: i materiali NON di pagamento mantengono il comportamento
    storico (upload -> RECEIVED)."""
    contract, _, materiale = contratto_con_saldo
    client.force_login(user_sponsor)

    resp = client.post(
        reverse('portal:material_upload', args=[materiale.id]),
        {'files': _pdf_finto('logo.pdf')},
    )
    assert resp.status_code == 302
    materiale.refresh_from_db()
    assert materiale.status == DeadlineStatus.RECEIVED


@pytest.mark.django_db
def test_pagina_materiali_mostra_nota_verifica(client, user_sponsor, contratto_con_saldo):
    """Dopo l'upload della contabile la pagina mostra la nota 'in attesa di
    verifica' e non il badge Pagato."""
    contract, saldo, _ = contratto_con_saldo
    client.force_login(user_sponsor)
    client.post(reverse('portal:material_upload', args=[saldo.id]), {'files': _pdf_finto()})

    resp = client.get(reverse('portal:materials_list', args=[contract.id]))
    html = resp.content.decode()
    assert 'Contabile ricevuta' in html
    assert 'Pagato il' not in html
