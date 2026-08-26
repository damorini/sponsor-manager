"""Note per lo sponsor sullo Stand + ordinamento naturale dei codici.

- Stand/StandBlock hanno il campo 'sponsor_notes' (IT/EN), separato dalle
  note interne; le note compaiono nel PREVENTIVO e nella DOMANDA/contratto.
- Ordinamento naturale: S-1..S-9, S-10 restano insieme agli S (prima il
  prefisso testuale, poi il numero come intero) - prima S-10 finiva dopo i D-.
- Il template Excel degli stand ha la colonna 'note_sponsor' e l'import la carica.
"""
from datetime import date
from decimal import Decimal

import pytest

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event, EventType
from sponsors.models import Contact
from venues.models import Stand


def _leggi_pdf(doc):
    from pathlib import Path
    from django.conf import settings
    from pypdf import PdfReader
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1)
    return ' '.join((p.extract_text() or '') for p in
                    PdfReader(str(Path(settings.MEDIA_ROOT) / rel)).pages)


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Note Stand', 'en': 'Ev Note Stand'}, code='NST',
        event_type=EventType.NON_ECM,
        start_date=date(2026, 11, 1), end_date=date(2026, 11, 2),
    )


@pytest.mark.django_db
def test_ordinamento_naturale_codici(evento):
    for code in ['S-10', 'D-2', 'S-2', 'S-1', 'D-1', 'S-9']:
        Stand.objects.create(event=evento, code=code,
                             base_price=Decimal('100.00'))
    codici = list(Stand.objects.filter(event=evento).values_list('code', flat=True))
    assert codici == ['D-1', 'D-2', 'S-1', 'S-2', 'S-9', 'S-10']


@pytest.mark.django_db
def test_note_sponsor_nel_preventivo_e_nella_domanda(
        sponsor, dati_firmatario_completi, evento):
    Contact.objects.create(
        sponsor=sponsor, full_name='Firmatario Note', email='firm_note@test.it',
        is_signer=True, **dati_firmatario_completi,
    )
    stand = Stand.objects.create(
        event=evento, code='N-01', base_price=Decimal('1000.00'),
        sponsor_notes={'it': 'Grafiche pannello: PDF 300 dpi entro il 10/10',
                       'en': 'Panel graphics: PDF 300 dpi by 10/10'},
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='NST-26-001',
        stand=stand,
    )

    from contracts.services.pdf_generator import (
        generate_admission_request_pdf, generate_quote_pdf_html)

    doc_prev = generate_quote_pdf_html(contract)
    testo_prev = _leggi_pdf(doc_prev)
    assert 'Grafiche pannello: PDF 300 dpi entro il 10/10' in testo_prev
    assert 'Note sullo spazio espositivo' in testo_prev

    doc_dom = generate_admission_request_pdf(contract)
    testo_dom = _leggi_pdf(doc_dom)
    assert 'Grafiche pannello: PDF 300 dpi entro il 10/10' in testo_dom


@pytest.mark.django_db
def test_domanda_senza_note_non_mostra_etichetta(
        sponsor, dati_firmatario_completi, evento):
    Contact.objects.create(
        sponsor=sponsor, full_name='Firmatario NoNote', email='firm_nonote@test.it',
        is_signer=True, **dati_firmatario_completi,
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='NST-26-002',
    )
    from contracts.services.pdf_generator import generate_admission_request_pdf
    doc = generate_admission_request_pdf(contract)
    assert 'Note sullo spazio espositivo' not in _leggi_pdf(doc)


@pytest.mark.django_db
def test_template_excel_e_import_note_sponsor(tmp_path, evento):
    from catalog.utils.excel_template import build_template_stand_workbook
    from django.core.management import call_command
    from openpyxl import Workbook

    # 1. il modello scaricabile ha la colonna
    wb = build_template_stand_workbook()
    header = [c.value for c in wb.active[1]]
    assert 'note_sponsor' in header

    # 2. l'import carica la nota
    wb2 = Workbook()
    ws = wb2.active
    ws.append(['evento_slug', 'code', 'prezzo_base', 'note_sponsor'])
    ws.append([evento.slug, 'X-01', '1200.00', 'Portare grafiche in PDF'])
    f = tmp_path / 'stand_note.xlsx'
    wb2.save(str(f))
    call_command('importa_stand', '--file', str(f))
    stand = Stand.objects.get(event=evento, code='X-01')
    assert stand.sponsor_notes.get('it') == 'Portare grafiche in PDF'
