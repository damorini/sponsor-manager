"""Preventivo PDF: sotto 'Riepilogo spazi e servizi in opzione' c'e' la frase
che spiega spazi opzionati, servizi collegati e inclusi."""
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest

from contracts.models import Contract, ContractKind, ContractStatus
from events.models import Event


@pytest.fixture
def evento(db):
    return Event.objects.create(
        name={'it': 'Ev Frase', 'en': 'Ev Frase'}, code='FRS',
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )


@pytest.mark.parametrize('lingua,frase', [
    ('it', 'Di seguito trovate la descrizione degli spazi opzionati'),
    ('en', 'Below you will find the description of the spaces on option'),
])
def test_frase_sotto_il_riepilogo(sponsor, evento, lingua, frase, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, language=lingua)
    catturato = {}

    class FintoHTML:
        def __init__(self, string, base_url=None):
            catturato['html'] = string

        def write_pdf(self):
            return b'%PDF-1.4'

    from contracts.services.pdf_generator import generate_quote_pdf_html
    with mock.patch('weasyprint.HTML', FintoHTML):
        generate_quote_pdf_html(c)
    html = catturato['html']
    assert frase in html
    assert html.index(frase) > html.index('section-title')


def test_descrizione_riga_va_a_capo(sponsor, evento, settings, tmp_path):
    """I servizi inclusi scritti uno per riga restano uno per riga."""
    from contracts.models import ContractLine
    settings.MEDIA_ROOT = tmp_path
    c = Contract.objects.create(
        sponsor=sponsor, event=evento, contract_kind=ContractKind.MAIN,
        status=ContractStatus.DRAFT, language='it')
    ContractLine.objects.create(
        contract=c, service_name_snapshot='Spazio espositivo - 1-A',
        service_description_snapshot='· Area nuda\n· Logo su sito',
        quantity=1, unit_price=Decimal('1000.00'))
    catturato = {}

    class FintoHTML:
        def __init__(self, string, base_url=None):
            catturato['html'] = string

        def write_pdf(self):
            return b'%PDF-1.4'

    from contracts.services.pdf_generator import generate_quote_pdf_html
    with mock.patch('weasyprint.HTML', FintoHTML):
        generate_quote_pdf_html(c)
    assert '· Area nuda<br>· Logo su sito' in catturato['html']
