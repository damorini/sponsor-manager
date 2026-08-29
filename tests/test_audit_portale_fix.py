"""Regressioni dell'audit portale del 29/08 (pacchetto A).

Copre i bug confermati dalla revisione multi-agente:
- scadenza ESONERATA non e' "da pagare"
- next=//evil.com rifiutato al login (open redirect)
- ?event=<non-UUID> non fa 500
- cart_add non si fonde con la riga "inclusa" a 0 EUR
- cart_update rispetta la disponibilita'
- archivio eventi non mostra le bozze
- documenti "solo interno" invisibili al cliente (lista + media protetti)
- upload rifiutato su contratti annullati
- avvio pagamento bloccato senza anagrafica completa
- carrelli abbandonati da 14+ giorni vengono chiusi (scorte liberate)
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import Service, ServiceInclusion
from contracts.models import (Contract, ContractKind, ContractLine,
                              ContractStatus, Deadline, DeadlineStatus)
from events.models import Event, EventStatus
from sponsors.models import Contact

DOMANI = date.today() + timedelta(days=120)


def _privacy_ok():
    from core.models import OrganizerSettings
    return {
        'privacy_accepted_at': timezone.now(),
        'privacy_policy_version': OrganizerSettings.load().privacy_policy_version or '1.0',
    }


def _completa_anagrafica(sponsor):
    for campo, valore in [
        ('vat_number', '01234567890'), ('sdi_code', '0000000'),
        ('pec_email', 'pec@test.it'), ('address_street', 'Via Test 1'),
        ('address_city', 'Bologna'), ('address_zip', '40100'),
        ('address_province', 'BO'), ('address_country', 'Italia'),
        ('website', 'https://test.it'), ('business_description', 'Test'),
    ]:
        if not getattr(sponsor, campo, None):
            setattr(sponsor, campo, valore)
    sponsor.save()


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Audit', 'en': 'Ev Audit'}, code='AUD',
        status=EventStatus.SELLING,
        start_date=DOMANI, end_date=DOMANI + timedelta(days=1))


@pytest.fixture
def contratto_main(db, sponsor, evento, user_sponsor, contact):
    Contact.objects.filter(portal_user=user_sponsor).update(roles=['operational'])
    _completa_anagrafica(sponsor)
    return Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='AUD-26-001',
        subtotal=Decimal('1000.00'), vat_amount=Decimal('220.00'),
        total=Decimal('1220.00'), deposit_percent=Decimal('50.00'))


# ---------------------------------------------------------------------------
# 1. Scadenza esonerata non e' "da pagare"
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scadenza_esonerata_non_pagabile(contratto_main):
    from portal.views.contract import _compute_payment_due
    Deadline.objects.create(
        contract=contratto_main, deadline_type='pagamento_acconto',
        title='Acconto', due_date=date.today(), status=DeadlineStatus.WAIVED)
    Deadline.objects.create(
        contract=contratto_main, deadline_type='pagamento_saldo',
        title='Saldo', due_date=DOMANI, status=DeadlineStatus.WAIVED)
    assert _compute_payment_due(contratto_main) is None

    # acconto esonerato + saldo aperto -> propone il SALDO, non l'acconto
    contratto_main.deadlines.filter(deadline_type='pagamento_saldo').update(
        status=DeadlineStatus.PENDING)
    due = _compute_payment_due(contratto_main)
    assert due is not None and due['type'] == 'saldo'


# ---------------------------------------------------------------------------
# 2. Open redirect rifiutato al login
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_rifiuta_next_esterno(client, user_sponsor, contact):
    resp = client.post(
        reverse('portal:login') + '?next=//evil.com/phish',
        {'username': user_sponsor.email, 'password': 'TestPassword123!'})
    assert resp.status_code == 302
    assert not resp.url.startswith('//')


# ---------------------------------------------------------------------------
# 3. ?event= malformato non fa 500
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_filtro_evento_malformato_non_crasha(client_authenticated):
    resp = client_authenticated.get(
        reverse('portal:contracts_list') + '?event=non-un-uuid')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. cart_add non tocca la riga inclusa a 0 EUR
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cart_add_non_fonde_riga_inclusa(client, user_sponsor, sponsor, evento):
    Contact.objects.create(portal_user=user_sponsor, sponsor=sponsor,
                           full_name='Op Cart', email='opcart@test.it',
                           roles=['operational'], **_privacy_ok())
    _completa_anagrafica(sponsor)
    Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='AUD-26-002')
    padre = Service.objects.create(
        event=evento, code='PADRE-A', name={'it': 'Padre', 'en': 'P'},
        base_price=Decimal('500.00'), is_self_purchasable=True)
    figlio = Service.objects.create(
        event=evento, code='FIGLIO-A', name={'it': 'Figlio', 'en': 'F'},
        base_price=Decimal('100.00'), is_self_purchasable=True)
    ServiceInclusion.objects.create(parent=padre, child=figlio, quantity=1)

    client.force_login(user_sponsor)
    client.post(reverse('portal:cart_add'), {'service_id': str(padre.id),
                                             'quantity': 1})
    client.post(reverse('portal:cart_add'), {'service_id': str(figlio.id),
                                             'quantity': 1})

    cart = Contract.objects.get(sponsor=sponsor, event=evento,
                                contract_kind=ContractKind.ADDON)
    righe_figlio = cart.lines.filter(service=figlio)
    # DUE righe: quella inclusa (0 EUR) e quella COMPRATA a prezzo pieno
    assert righe_figlio.count() == 2
    prezzi = sorted(l.unit_price for l in righe_figlio)
    assert prezzi[0] == Decimal('0.00') and prezzi[1] == Decimal('100.00')


# ---------------------------------------------------------------------------
# 5. cart_update rispetta la disponibilita'
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cart_update_clampa_alla_disponibilita(client, user_sponsor, sponsor, evento):
    Contact.objects.create(portal_user=user_sponsor, sponsor=sponsor,
                           full_name='Op Upd', email='opupd@test.it',
                           roles=['operational'], **_privacy_ok())
    _completa_anagrafica(sponsor)
    Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.ACTIVE, contract_number='AUD-26-003')
    srv = Service.objects.create(
        event=evento, code='LIMITATO', name={'it': 'Limitato', 'en': 'L'},
        base_price=Decimal('50.00'), is_self_purchasable=True,
        total_available=3)
    client.force_login(user_sponsor)
    client.post(reverse('portal:cart_add'), {'service_id': str(srv.id),
                                             'quantity': 1})
    cart = Contract.objects.get(sponsor=sponsor, event=evento,
                                contract_kind=ContractKind.ADDON)
    line = cart.lines.get(service=srv)
    client.post(reverse('portal:cart_update_quantity', args=[line.id]),
                {'quantity': 50})
    line.refresh_from_db()
    assert line.quantity == 3  # clampata al disponibile, non 50


# ---------------------------------------------------------------------------
# 6. Archivio eventi: niente bozze
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_archivio_non_mostra_bozze(client, user_sponsor, sponsor, contact):
    ev = Event.objects.create(
        name={'it': 'Ev Arch', 'en': 'Ev Arch'}, code='ARCH',
        status=EventStatus.ARCHIVED,
        start_date=date(2025, 1, 1), end_date=date(2025, 1, 2))
    Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.COMPLETED, contract_number='ARCH-25-001')
    Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='ARCH-25-BOZZA')
    client.force_login(user_sponsor)
    resp = client.get(reverse('portal:archived_event_detail', args=[ev.id]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'ARCH-25-001' in html
    assert 'ARCH-25-BOZZA' not in html


# ---------------------------------------------------------------------------
# 7. Documenti "solo interno" invisibili al cliente
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_documento_interno_invisibile(client, user_sponsor, contratto_main):
    from django.contrib.contenttypes.models import ContentType
    from shared.models import Document
    dl = Deadline.objects.create(
        contract=contratto_main, deadline_type='tecnica', title='Logo',
        due_date=DOMANI, status=DeadlineStatus.PENDING)
    ct = ContentType.objects.get_for_model(Deadline)
    doc = Document.objects.create(
        content_type=ct, object_id=dl.pk, title='nota-interna.pdf',
        file_name='nota-interna.pdf', mime_type='application/pdf',
        storage_url='/media/documents/deadlines/nota-interna.pdf',
        document_type='sponsor_material', is_visible_to_sponsor=False)
    client.force_login(user_sponsor)
    # lista materiali: non compare
    resp = client.get(reverse('portal:materials_list', args=[contratto_main.pk]))
    assert 'nota-interna.pdf' not in resp.content.decode()
    # download diretto: 404
    resp = client.get(reverse('portal:material_download', args=[doc.pk]))
    assert resp.status_code == 404
    # media protetto: 404 per il cliente
    resp = client.get('/media/documents/deadlines/nota-interna.pdf')
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8. Upload rifiutato su contratto annullato
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_upload_su_contratto_annullato_403(client, user_sponsor, contratto_main):
    dl = Deadline.objects.create(
        contract=contratto_main, deadline_type='tecnica', title='Banner',
        due_date=DOMANI, status=DeadlineStatus.PENDING)
    contratto_main.status = ContractStatus.CANCELLED
    contratto_main.save(update_fields=['status'])
    client.force_login(user_sponsor)
    resp = client.post(reverse('portal:material_upload', args=[dl.pk]))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 9. Avvio pagamento bloccato senza anagrafica completa
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_bonifico_bloccato_senza_anagrafica(client, user_sponsor, sponsor, evento):
    Contact.objects.create(portal_user=user_sponsor, sponsor=sponsor,
                           full_name='Op Gate', email='opgate@test.it',
                           roles=['operational'], **_privacy_ok())
    # anagrafica NON completata di proposito
    sponsor.website = ''
    sponsor.save(update_fields=['website'])
    cart = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT, contract_number='AUD-26-004')
    srv = Service.objects.create(
        event=evento, code='GATE', name={'it': 'Gate', 'en': 'G'},
        base_price=Decimal('10.00'))
    ContractLine.objects.create(contract=cart, service=srv, quantity=1)
    client.force_login(user_sponsor)
    resp = client.post(reverse('portal:checkout_bank_transfer', args=[cart.pk]))
    assert resp.status_code == 302 and resp.url == reverse('portal:profile')
    cart.refresh_from_db()
    assert cart.status == ContractStatus.DRAFT  # NON convertito in ordine


# ---------------------------------------------------------------------------
# 10. Carrelli abbandonati da 14+ giorni chiusi (scorte liberate)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_carrello_abbandonato_liberato(sponsor, evento, contact):
    from contracts.payments import CartSession, CartSessionStatus
    from contracts.tasks.scheduled import check_abandoned_carts
    srv = Service.objects.create(
        event=evento, code='UNICO', name={'it': 'Unico', 'en': 'U'},
        base_price=Decimal('100.00'), total_available=1)
    cart_contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.ADDON,
        status=ContractStatus.DRAFT, contract_number='AUD-26-005')
    ContractLine.objects.create(contract=cart_contract, service=srv, quantity=1)
    cs = CartSession.objects.create(
        contract=cart_contract, contact=contact,
        status=CartSessionStatus.ACTIVE,
        last_activity_at=timezone.now() - timedelta(days=20))
    # prima del task il pezzo risulta impegnato
    assert srv.quantity_available() == 0
    check_abandoned_carts()
    cs.refresh_from_db(); cart_contract.refresh_from_db()
    assert cs.status == CartSessionStatus.EXPIRED
    assert cart_contract.status == ContractStatus.CANCELLED
    assert srv.quantity_available() == 1  # scorte tornate libere
