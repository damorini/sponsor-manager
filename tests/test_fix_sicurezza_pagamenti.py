"""Regressioni per i fix di sicurezza/correttezza dell'audit di luglio:

1. mark_failed NON degrada un pagamento gia' SUCCEEDED (race return-URL/webhook)
2. capture con ORDER_ALREADY_CAPTURED = successo idempotente, non fallimento
3. ordine PayPal: breakdown/items solo se importo == totale contratto;
   items basati sull'imponibile post-sconto
4. cambio stato a 'Firmato' A MANO dall'admin esegue la cascata di firma
5. /media/documents/* servito solo a staff o sponsor proprietario
6. upload: estensioni in whitelist, nome su disco randomizzato
"""
import json
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.urls import reverse

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
from contracts.payments import Payment, PaymentMethodChoice, PaymentStatus
from events.models import Event


@pytest.fixture
def contratto_addon(db, sponsor):
    event = Event.objects.create(
        name={'it': 'Ev Sicurezza', 'en': 'Ev Sicurezza'}, code='SEC',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    main = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='SEC-26-001',
    )
    addon = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.ADDON,
        status=ContractStatus.PENDING_PAYMENT, parent_contract=main,
    )
    service = Service.objects.create(
        event=event, code='SRV-SEC', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('100.00'), vat_rate=Decimal('22.00'),
    )
    ContractLine.objects.create(
        contract=addon, service=service, quantity=2,
        unit_price=Decimal('100.00'), vat_rate=Decimal('22.00'),
        discount_percent=Decimal('10.00'),  # riga scontata: 180 imponibile
    )
    addon.refresh_from_db()
    return addon


# ---------------------------------------------------------------------------
# 1+2: race pagamenti
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_mark_failed_non_degrada_un_pagamento_riuscito(contratto_addon):
    p = Payment.objects.create(
        contract=contratto_addon, payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=contratto_addon.total, status=PaymentStatus.SUCCEEDED,
    )
    p.mark_failed(reason='ORDER_ALREADY_CAPTURED simulato')
    p.refresh_from_db()
    assert p.status == PaymentStatus.SUCCEEDED


@pytest.mark.django_db
def test_capture_gia_catturato_diventa_successo_idempotente(contratto_addon):
    from contracts.services.paypal_service import capture_paypal_order
    p = Payment.objects.create(
        contract=contratto_addon, payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=contratto_addon.total, status=PaymentStatus.PENDING,
        paypal_order_id='ORD-TEST-1',
    )
    fake_client = mock.Mock()
    fake_client.orders.capture_order.side_effect = RuntimeError(
        "422 UNPROCESSABLE_ENTITY ORDER_ALREADY_CAPTURED")
    with mock.patch('contracts.services.paypal_service.get_paypal_client',
                    return_value=fake_client):
        result = capture_paypal_order('ORD-TEST-1')
    assert result['already_processed'] is True
    p.refresh_from_db()
    assert p.status == PaymentStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 3: breakdown PayPal coerente
# ---------------------------------------------------------------------------

def _mock_create_order_client(catturato):
    """Client PayPal finto che salva il body ricevuto e risponde un ordine."""
    fake_client = mock.Mock()

    def _create(payload):
        catturato.append(payload['body'])
        resp = mock.Mock()
        resp.text = json.dumps({'id': 'ORD-NEW', 'links': [
            {'rel': 'approve', 'href': 'https://paypal.test/approve'}]})
        return resp

    fake_client.orders.create_order.side_effect = _create
    return fake_client


@pytest.mark.django_db
def test_ordine_importo_parziale_senza_breakdown(contratto_addon):
    from contracts.services.paypal_service import create_paypal_order
    parziale = contratto_addon.total - Decimal('50.00')
    p = Payment.objects.create(
        contract=contratto_addon, payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=parziale, status=PaymentStatus.PENDING,
    )
    catturato = []
    with mock.patch('contracts.services.paypal_service.get_paypal_client',
                    return_value=_mock_create_order_client(catturato)):
        create_paypal_order(p)
    unit = catturato[0]['purchase_units'][0]
    assert 'breakdown' not in unit['amount'], \
        "con importo parziale il breakdown va omesso (PayPal rifiuterebbe)"
    assert 'items' not in unit


@pytest.mark.django_db
def test_ordine_totale_con_sconto_items_coerenti(contratto_addon):
    from contracts.services.paypal_service import create_paypal_order
    p = Payment.objects.create(
        contract=contratto_addon, payment_method=PaymentMethodChoice.PAYPAL,
        amount_gross=contratto_addon.total, status=PaymentStatus.PENDING,
    )
    catturato = []
    with mock.patch('contracts.services.paypal_service.get_paypal_client',
                    return_value=_mock_create_order_client(catturato)):
        create_paypal_order(p)
    unit = catturato[0]['purchase_units'][0]
    assert unit['amount']['breakdown']['item_total']['value'] == str(contratto_addon.subtotal)
    somma_items = sum(Decimal(i['unit_amount']['value']) * int(i['quantity'])
                      for i in unit['items'])
    assert somma_items == contratto_addon.subtotal, \
        "gli items devono sommare all'imponibile POST-sconto"


# ---------------------------------------------------------------------------
# 4: cambio stato a mano dall'admin
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stato_firmato_a_mano_esegue_cascata(sponsor):
    from django.contrib.admin.sites import AdminSite
    from django.test import RequestFactory
    from contracts.admin import ContractAdmin
    from venues.models import Stand

    event = Event.objects.create(
        name={'it': 'Ev Cascata', 'en': 'Ev Cascata'}, code='CSC',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    stand = Stand.objects.create(event=event, code='C-01', base_price=Decimal('1000.00'))
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT, contract_number='CSC-26-001',
        stand=stand,
    )
    assert not contract.deadlines.filter(deadline_type='pagamento_saldo').exists()

    admin_obj = ContractAdmin(Contract, AdminSite())
    admin_obj.message_user = lambda *a, **k: None
    request = RequestFactory().post('/')

    # simula l'operatore che cambia il menu a tendina Stato -> Firmato e salva
    contract.status = ContractStatus.SIGNED
    admin_obj.save_model(request, contract, form=None, change=True)

    contract.refresh_from_db()
    assert contract.signed_date is not None
    assert contract.deadlines.filter(deadline_type='pagamento_saldo').exists(), \
        "la cascata della firma deve generare le scadenze di pagamento"
    assert contract.deadlines.filter(deadline_type='contratto_firmato').exists()
    stand.refresh_from_db()
    assert stand.status == 'assigned'


# ---------------------------------------------------------------------------
# 5: media protetti
# ---------------------------------------------------------------------------

@pytest.fixture
def documento_su_contratto(db, sponsor, contratto_addon, tmp_path, settings):
    from django.contrib.contenttypes.models import ContentType
    from shared.models import Document
    settings.MEDIA_ROOT = str(tmp_path)
    rel = f"documents/contracts/{contratto_addon.id}/riservato.pdf"
    full = tmp_path / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(b'%PDF-1.4 segreto')
    ct = ContentType.objects.get_for_model(Contract)
    doc = Document.objects.create(
        content_type=ct, object_id=contratto_addon.id,
        title='riservato.pdf', file_name='riservato.pdf',
        file_size_bytes=16, mime_type='application/pdf',
        storage_url=settings.MEDIA_URL + rel, document_type='sponsor_contract',
    )
    return doc, '/media/' + rel


@pytest.mark.django_db
def test_media_documenti_richiede_login(client, documento_su_contratto):
    _doc, url = documento_su_contratto
    resp = client.get(url)
    assert resp.status_code == 302 and '/login' in resp.url


@pytest.mark.django_db
def test_media_documenti_proprietario_ok(client, user_sponsor, contact, documento_su_contratto):
    _doc, url = documento_su_contratto
    client.force_login(user_sponsor)
    resp = client.get(url)
    assert resp.status_code == 200
    assert 'attachment' in resp['Content-Disposition']


@pytest.mark.django_db
def test_media_documenti_altro_sponsor_404(client, documento_su_contratto):
    from django.contrib.auth import get_user_model
    from sponsors.models import Sponsor, Contact
    from users.models import UserRole
    _doc, url = documento_su_contratto
    altro_user = get_user_model().objects.create_user(
        username='intruso', email='intruso@test.it', password='x', is_active=True)
    altro_user.role = UserRole.SPONSOR
    altro_user.save()
    altro_sponsor = Sponsor.objects.create(legal_name='Intrusi Srl', vat_number='999',
                                           address_country='IT')
    Contact.objects.create(portal_user=altro_user, sponsor=altro_sponsor,
                           full_name='Intruso Uno', email='intruso@test.it')
    client.force_login(altro_user)
    resp = client.get(url)
    assert resp.status_code == 404


@pytest.mark.django_db
def test_media_documenti_staff_ok(client, documento_su_contratto):
    from django.contrib.auth import get_user_model
    _doc, url = documento_su_contratto
    staff = get_user_model().objects.create_user(
        username='op_media', email='op_media@test.it', password='x',
        is_active=True, is_staff=True)
    client.force_login(staff)
    assert client.get(url).status_code == 200


# ---------------------------------------------------------------------------
# 6: upload irrobustito
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_upload_estensione_vietata_rifiutata(client, user_sponsor, sponsor, contact):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from contracts.models import Deadline, DeadlineStatus
    event = Event.objects.create(
        name={'it': 'Ev Upl', 'en': 'Ev Upl'}, code='UPL',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='UPL-26-001',
    )
    dl = Deadline.objects.create(
        contract=contract, deadline_type='tecnica', title='Invio logo',
        due_date=date(2026, 10, 1), status=DeadlineStatus.PENDING,
    )
    client.force_login(user_sponsor)
    malizioso = SimpleUploadedFile('exploit.html', b'<script>alert(1)</script>',
                                   content_type='application/pdf')
    client.post(reverse('portal:material_upload', args=[dl.id]), {'files': malizioso})
    from shared.models import Document
    from django.contrib.contenttypes.models import ContentType
    dl_ct = ContentType.objects.get_for_model(Deadline)
    assert not Document.objects.filter(content_type=dl_ct, object_id=dl.id).exists(), \
        "un .html spacciato per PDF non deve essere accettato"

    # un PDF vero passa, e il nome SU DISCO e' randomizzato
    buono = SimpleUploadedFile('contabile.pdf', b'%PDF-1.4 ok',
                               content_type='application/pdf')
    client.post(reverse('portal:material_upload', args=[dl.id]), {'files': buono})
    doc = Document.objects.filter(content_type=dl_ct, object_id=dl.id).first()
    assert doc is not None
    assert doc.file_name == 'contabile.pdf'
    assert 'contabile.pdf' not in doc.storage_url, \
        "il nome sul disco deve essere randomizzato, non quello originale"
    assert doc.storage_url.endswith('.pdf')
