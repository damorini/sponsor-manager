"""Pagina del contratto: colonna Ordine sulle righe, prezzo svuotato a mano
che torna il listino, PDF gia' sostituito che si puo' spuntare da cancellare."""
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def admin_client_righe(db, client):
    from django.contrib.auth import get_user_model
    utente = get_user_model().objects.create_superuser(
        username='boss_righe', email='boss.righe@test.it',
        password='AdminPass123!')
    client.force_login(utente)
    return client


def _contratto(sponsor):
    from catalog.models import Service
    from contracts.models import Contract, ContractKind, ContractLine, ContractStatus
    from events.models import Event

    ev = Event.objects.create(name={'it': 'Ev'}, code='ORDR',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    c = Contract.objects.create(sponsor=sponsor, event=ev, language='it',
                                contract_kind=ContractKind.MAIN, status=ContractStatus.DRAFT)
    righe = {}
    for code, prezzo in (('STAND', '1000'), ('BADGE', '0'), ('WIFI', '1500')):
        s = Service.objects.create(event=ev, code=code, name={'it': code},
                                   base_price=Decimal(prezzo), is_active=True)
        righe[code] = ContractLine.objects.create(contract=c, service=s, quantity=1)
    return c, righe


@pytest.mark.django_db
def test_colonna_ordine_nella_pagina_del_contratto(admin_client_righe, sponsor):
    c, _ = _contratto(sponsor)
    r = admin_client_righe.get(f'/admin/contracts/contract/{c.pk}/change/')
    assert r.status_code == 200
    assert b'lines-0-display_order' in r.content


@pytest.mark.django_db
def test_riepilogo_segue_l_ordine(sponsor):
    from contracts.models import ContractLine
    from contracts.services.pdf_generator import _righe_valorizzate_prima

    c, righe = _contratto(sponsor)
    for code, n in (('BADGE', 1), ('WIFI', 2), ('STAND', 3)):
        ContractLine.objects.filter(pk=righe[code].pk).update(display_order=n)

    ordine = [l.service.code for l in _righe_valorizzate_prima(c.lines.all())]
    assert ordine == ['BADGE', 'WIFI', 'STAND']


@pytest.mark.django_db
def test_prezzo_svuotato_torna_il_listino(sponsor):
    c, righe = _contratto(sponsor)
    riga = righe['WIFI']
    riga.unit_price = None
    riga.save()
    riga.refresh_from_db()
    assert riga.unit_price == Decimal('1500.00')


@pytest.mark.django_db
def test_pdf_gia_sostituito_da_cancellare_non_rompe(sponsor):
    from django.contrib.admin.sites import site
    from contracts.models import Contract
    from shared.models import Document

    c, _ = _contratto(sponsor)

    class FormsetFinto:
        model = Document
        forms = []
        deleted_objects = [Document(document_type='quote', title='vecchio.pdf',
                                    file_name='vecchio.pdf', storage_url='http://x/vecchio.pdf')]

        def save(self, commit=True):
            return []

        def save_m2m(self):
            pass

    class FormFinto:
        instance = c

    site._registry[Contract].save_formset(None, FormFinto(), FormsetFinto(), True)
    assert not Document.all_objects.filter(title='vecchio.pdf').exists()
