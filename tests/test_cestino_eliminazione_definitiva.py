"""Regressione 31/08: dal CESTINO l'eliminazione non faceva nulla.

L'admin rifaceva un soft-delete su record gia' cancellati: Django confermava
"eliminato con successo" ma le righe restavano nel cestino. Ora la seconda
eliminazione e' quella definitiva (record + documenti/comunicazioni collegati
via GenericForeignKey, che il cascade del DB non tocca)."""
from datetime import date, timedelta

import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from shared.models import Document

DOPO = date.today() + timedelta(days=60)


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_superuser(
        username='op_cest', email='op_cest@test.it', password='x')


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Cestino', 'en': 'Ev Cestino'}, code='CEST',
        start_date=DOPO, end_date=DOPO + timedelta(days=1))


def _elimina(client, pks, dal_cestino=False):
    """Riproduce l'uso reale: l'azione parte dalla pagina in cui ci si trova,
    quindi dal cestino l'URL porta ?trash=cestino (senza, la lista mostra
    solo gli attivi e i record cancellati non sono nemmeno selezionabili)."""
    url = reverse('admin:contracts_contract_changelist')
    if dal_cestino:
        url += '?trash=cestino'
    return client.post(url, {
        'action': 'delete_selected',
        ACTION_CHECKBOX_NAME: [str(p) for p in pks],
        'post': 'yes',
    }, follow=True)


@pytest.mark.django_db
def test_primo_delete_va_nel_cestino(client, staff, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='CEST-26-001')
    client.force_login(staff)
    _elimina(client, [c.pk])
    c.refresh_from_db()
    assert c.deleted_at is not None                      # nel cestino
    assert Contract.all_objects.filter(pk=c.pk).exists()  # ma ancora in DB


@pytest.mark.django_db
def test_dal_cestino_elimina_davvero(client, staff, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='CEST-26-002')
    ct = ContentType.objects.get_for_model(Contract)
    doc = Document.objects.create(
        content_type=ct, object_id=c.pk, title='doc.pdf', file_name='doc.pdf',
        mime_type='application/pdf', storage_url='/media/documents/doc.pdf',
        document_type='contract_pdf')
    c.delete()          # gia' nel cestino
    assert c.deleted_at is not None

    client.force_login(staff)
    _elimina(client, [c.pk], dal_cestino=True)

    assert not Contract.all_objects.filter(pk=c.pk).exists()   # sparito davvero
    assert not Document.all_objects.filter(pk=doc.pk).exists()  # niente orfani


@pytest.mark.django_db
def test_contratto_con_incassi_non_esplode(client, staff, sponsor, evento):
    """Un contratto nel cestino con PAGAMENTI registrati e' protetto dal DB
    (Payment.contract = PROTECT): l'eliminazione definitiva deve essere
    fermata con un avviso, non con un errore 500."""
    from decimal import Decimal
    from contracts.payments import (Payment, PaymentMethodChoice, PaymentStatus)
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='CEST-26-004',
        total=Decimal('100.00'))
    Payment.objects.create(
        contract=c, payment_method=PaymentMethodChoice.BANK_TRANSFER,
        amount_gross=Decimal('50.00'), status=PaymentStatus.SUCCEEDED)
    c.delete()  # nel cestino

    client.force_login(staff)
    url = reverse('admin:contracts_contract_changelist') + '?trash=cestino'
    # la conferma avvisa che ci sono record protetti
    resp = client.post(url, {'action': 'delete_selected',
                             ACTION_CHECKBOX_NAME: [str(c.pk)]})
    assert resp.status_code == 200
    testo = resp.content.decode().lower()
    assert 'impossibile' in testo or 'protett' in testo
    # e comunque nessun crash, il contratto resta nel cestino
    resp = _elimina(client, [c.pk], dal_cestino=True)
    assert resp.status_code == 200
    assert Contract.all_objects.filter(pk=c.pk).exists()


@pytest.mark.django_db
def test_pagina_conferma_avvisa_che_e_definitiva(client, staff, sponsor, evento):
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, contract_number='CEST-26-003')
    c.delete()
    client.force_login(staff)
    resp = client.post(
        reverse('admin:contracts_contract_changelist') + '?trash=cestino', {
            'action': 'delete_selected',
            ACTION_CHECKBOX_NAME: [str(c.pk)],
        })
    assert resp.status_code == 200
    html = resp.content.decode()
    # e' davvero la conferma per QUESTO contratto, non una pagina qualsiasi
    assert 'CEST-26-003' in html
    assert 'DEFINITIVAMENTE' in html
    # senza conferma finale il record e' ancora li'
    assert Contract.all_objects.filter(pk=c.pk).exists()
