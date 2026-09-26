"""Caratteristiche complete dello spazio (misure, tipologia, altezza max,
kW, acqua, internet, altre) nel Regolamento tecnico e nel PASS allestimento."""
from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from docx import Document

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event
from venues.models import Stand


@pytest.fixture
def contratto(db, sponsor, contact):
    ev = Event.objects.create(name={'it': 'Ev Spazio'}, code='SPA',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    st = Stand.objects.create(
        event=ev, code='1-A', base_price=Decimal('1000'), stand_type='Spazio Main-XL',
        width_meters=Decimal('6.00'), depth_meters=Decimal('4.00'),
        max_height_meters=Decimal('3.50'), has_power=True, power_kw=Decimal('3.00'),
        has_water=False, has_internet=True, access_door='3',
        caratteristiche='2 lati liberi\nPavimento in moquette')
    return Contract.objects.create(sponsor=sponsor, event=ev, stand=st,
                                   contract_kind=ContractKind.MAIN,
                                   status=ContractStatus.SIGNED, contract_number='SPA-001')


def test_voci_complete(contratto):
    from contracts.services.caratteristiche_spazio import schede
    voci = dict(schede(contratto)[0]['voci'])
    assert voci['Tipologia'] == 'Spazio Main-XL'
    assert voci['Misure'] == '6 × 4 m (24 m²)'
    assert voci['Altezza max di allestimento'] == '3,5 m'
    assert voci['Allaccio elettrico'] == '3 kW'
    assert voci['Allaccio idrico'] == 'no'
    assert voci['Internet'] == 'sì'
    assert voci['Altre caratteristiche'].startswith('2 lati liberi')


def test_nel_regolamento(contratto, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    from contracts.services.allegato2 import prepara_docx
    d0 = Document()
    d0.add_paragraph('REGOLAMENTO TECNICO', style='Title')
    d0.add_paragraph('1. GLOSSARIO')
    percorso = tmp_path / 'a2.docx'
    d0.save(str(percorso))
    prepara_docx(percorso, contratto)
    testo = '\n'.join(p.text for p in Document(str(percorso)).paragraphs)
    riga = next(r for r in testo.splitlines() if r.startswith('Caratteristiche dello spazio'))
    for atteso in ('Misure: 6 × 4 m (24 m²)', 'Altezza max di allestimento: 3,5 m',
                   'Allaccio elettrico: 3 kW', 'Allaccio idrico: no', 'Internet: sì',
                   'Altre caratteristiche: 2 lati liberi – Pavimento in moquette'):
        assert atteso in riga, atteso
    assert 'Accesso al padiglione' not in riga      # e' gia' nella tabellina


def test_nel_pass(contratto):
    from contracts.services import pass_allestimento as pa
    pa.invia(contratto)
    html = mail.outbox[0].alternatives[0][0]
    assert 'Caratteristiche del vostro spazio' in html
    for atteso in ('6 × 4 m (24 m²)', '3,5 m', '3 kW', 'Pavimento in moquette'):
        assert atteso in html, atteso


def test_excel_colonna_altre_caratteristiche(contratto):
    from catalog.utils.excel_template import build_template_stand_workbook
    wb = build_template_stand_workbook()
    intest = [c.value for c in wb.active[1]]
    assert 'altre_caratteristiche' in intest
