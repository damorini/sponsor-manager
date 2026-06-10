"""
#3+#4: Segreteria Scientifica sull'Event, mostrata in basso a destra nel
footer del PDF preventivo grafico (quote_pdf.html).

- build_scientific_secretariat_context(event, site_url) costruisce il dict
  {'text', 'logo_url'} dai campi Event.scientific_secretariat[_logo], oppure
  None se entrambi mancano.
- Il template quote_pdf.html stampa il blocco scientifico SOLO se presente.
"""
import pytest
from types import SimpleNamespace
from decimal import Decimal
from datetime import date
from pathlib import Path
from django.conf import settings
from django.template.loader import render_to_string

from contracts.services.pdf_generator import (
    build_scientific_secretariat_context,
    generate_quote_pdf_html,
)


class _FakeLogo:
    """Finto FileField: vero come booleano, espone .url."""
    def __init__(self, url):
        self.url = url

    def __bool__(self):
        return True


# ---- helper di costruzione contesto (logica pura) -----------------------

def test_secretariat_context_none_when_empty():
    event = SimpleNamespace(scientific_secretariat='', scientific_secretariat_logo=None)
    assert build_scientific_secretariat_context(event) is None


def test_secretariat_context_from_text():
    event = SimpleNamespace(
        scientific_secretariat='Segreteria Scientifica\nVia Roma 1\ninfo@sci.it',
        scientific_secretariat_logo=None,
    )
    ctx = build_scientific_secretariat_context(event)
    assert ctx is not None
    assert 'Via Roma 1' in ctx['text']
    assert ctx['logo_url'] == ''


def test_secretariat_context_logo_absolute_url():
    event = SimpleNamespace(
        scientific_secretariat='X',
        scientific_secretariat_logo=_FakeLogo('/media/events/scientific_secretariat/l.png'),
    )
    ctx = build_scientific_secretariat_context(event, site_url='https://x.it')
    assert ctx['logo_url'] == 'https://x.it/media/events/scientific_secretariat/l.png'


def test_secretariat_context_logo_only():
    event = SimpleNamespace(
        scientific_secretariat='   ',
        scientific_secretariat_logo=_FakeLogo('/media/l.png'),
    )
    ctx = build_scientific_secretariat_context(event)
    assert ctx is not None
    assert ctx['logo_url'].endswith('/media/l.png')


# ---- rendering condizionale nel template --------------------------------

def _minimal_ctx(**over):
    ctx = {
        'org': {'name': 'VALET', 'logo_url': ''},
        'sci': None,
        't': {'ref': 'Preventivo'},
        'lines': [],
        'brand_color': '#1d6534',
    }
    ctx.update(over)
    return ctx


def test_quote_template_renders_scientific_block():
    html = render_to_string('quote_pdf.html', _minimal_ctx(
        sci={'text': 'Segreteria Scientifica ACME', 'logo_url': ''}))
    assert 'Segreteria Scientifica ACME' in html
    assert 'class="sec-right"' in html


def test_quote_template_omits_scientific_block_when_absent():
    html = render_to_string('quote_pdf.html', _minimal_ctx(sci=None))
    assert 'class="sec-right"' not in html


# ---- integrazione: Event reale -> PDF generato senza crash --------------

@pytest.mark.django_db
def test_quote_pdf_with_scientific_secretariat(sponsor):
    from events.models import Event
    from catalog.models import Service
    from contracts.models import Contract, ContractLine, ContractKind, ContractStatus

    event = Event.objects.create(
        name={'it': 'Sci Event', 'en': 'Sci Event'},
        code='SCI',
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 2),
        scientific_secretariat='Segreteria Scientifica Test\nVia Test 1, Bologna',
    )
    service = Service.objects.create(
        event=event,
        name={'it': 'Servizio Y', 'en': 'Service Y'},
        base_price=Decimal('100.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor,
        event=event,
        contract_kind=ContractKind.MAIN,
        status=ContractStatus.SENT,
        contract_number='SCI-26-001',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)

    doc = generate_quote_pdf_html(contract)
    assert doc.document_type == 'quote'
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1).lstrip('/')
    disk_path = Path(settings.MEDIA_ROOT) / rel
    assert disk_path.exists()
    assert disk_path.read_bytes()[:4] == b'%PDF'
