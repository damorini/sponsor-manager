"""
Template DOCX in inglese per contratti e domanda di ammissione.

- Esistono le versioni _en.docx dei 4 template e hanno ESATTAMENTE gli
  stessi segnaposti jinja delle versioni _it.docx (multiset identico).
- La selezione del template segue contract.language ('en' -> _en, fallback it).
- e2e: un contratto con language='en' produce domanda e contratto sponsor
  con i testi inglesi.
"""
import re
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from lxml import etree

from contracts.services import pdf_generator as pg

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
JINJA_RE = re.compile(r'\{\{.*?\}\}|\{%.*?%\}')

PAIRS = [
    ('template_ecm_it.docx', 'template_ecm_en.docx'),
    ('template_non_ecm_it.docx', 'template_non_ecm_en.docx'),
    ('template_contratto_sponsor_non_ecm_it.docx',
     'template_contratto_sponsor_non_ecm_en.docx'),
    ('template_domanda_ammissione_it.docx', 'template_domanda_ammissione_en.docx'),
]


def _jinja_tags(docx_path):
    """Multiset dei tag jinja (testo concatenato per paragrafo)."""
    tags = []
    zf = zipfile.ZipFile(docx_path)
    for name in sorted(zf.namelist()):
        if not re.fullmatch(r'word/(document|header\d*|footer\d*)\.xml', name):
            continue
        root = etree.fromstring(zf.read(name))
        for p in root.iter(f'{{{W}}}p'):
            text = ''.join(t.text or '' for t in p.iter(f'{{{W}}}t'))
            tags.extend(JINJA_RE.findall(text))
    return sorted(tags)


def _docx_text(docx_path):
    zf = zipfile.ZipFile(docx_path)
    root = etree.fromstring(zf.read('word/document.xml'))
    return ''.join(t.text or '' for t in root.iter(f'{{{W}}}t'))


@pytest.mark.parametrize('it_name,en_name', PAIRS)
def test_file_en_esiste(it_name, en_name):
    assert (pg.TEMPLATES_DIR / en_name).exists(), f'manca {en_name}'


@pytest.mark.parametrize('it_name,en_name', PAIRS)
def test_tag_jinja_identici(it_name, en_name):
    assert _jinja_tags(pg.TEMPLATES_DIR / it_name) == \
        _jinja_tags(pg.TEMPLATES_DIR / en_name)


def test_template_map_contiene_en():
    assert pg.TEMPLATE_MAP[('ecm', 'en')] == 'template_ecm_en.docx'
    assert pg.TEMPLATE_MAP[('non_ecm', 'en')] == 'template_non_ecm_en.docx'


def test_selezione_template_domanda_per_lingua():
    assert pg._admission_template_for('en') == 'template_domanda_ammissione_en.docx'
    assert pg._admission_template_for('it') == 'template_domanda_ammissione_it.docx'
    # lingua sconosciuta o vuota: fallback italiano
    assert pg._admission_template_for('de') == 'template_domanda_ammissione_it.docx'
    assert pg._admission_template_for('') == 'template_domanda_ammissione_it.docx'


def test_selezione_template_contratto_sponsor_per_lingua():
    assert pg._sponsor_contract_template_for('en') == \
        'template_contratto_sponsor_non_ecm_en.docx'
    assert pg._sponsor_contract_template_for('it') == \
        'template_contratto_sponsor_non_ecm_it.docx'
    assert pg._sponsor_contract_template_for(None) == \
        'template_contratto_sponsor_non_ecm_it.docx'


@pytest.fixture
def contratto_en(db, sponsor, dati_firmatario_completi):
    from sponsors.models import Contact
    from events.models import Event, EventType
    from catalog.models import Service
    from contracts.models import Contract, ContractLine, ContractKind, ContractStatus
    Contact.objects.create(
        sponsor=sponsor, full_name='John Smith',
        email='john@test.com', is_signer=True,
        **dati_firmatario_completi,
    )
    event = Event.objects.create(
        name={'it': 'Evento EN', 'en': 'EN Event'}, code='ENG',
        event_type=EventType.NON_ECM,
        start_date=date(2026, 11, 1), end_date=date(2026, 11, 2),
    )
    service = Service.objects.create(
        event=event, name={'it': 'Stand', 'en': 'Booth'},
        base_price=Decimal('800.00'),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='ENG-26-001',
        language='en',
    )
    ContractLine.objects.create(contract=contract, service=service, quantity=1)
    return contract


def _docx_generati(contract):
    d = Path(settings.MEDIA_ROOT) / f'documents/contracts/{contract.id}'
    return list(d.glob('*.docx')) if d.exists() else []


@pytest.mark.django_db
def test_domanda_in_inglese_per_contratto_en(contratto_en):
    doc = pg.generate_admission_request_pdf(contratto_en)
    assert doc is not None
    docx = [p for p in _docx_generati(contratto_en) if 'domanda' in p.name.lower()
            or 'admission' in p.name.lower()]
    assert docx, 'docx intermedio della domanda non trovato'
    testo = _docx_text(docx[0])
    assert 'APPLICATION FOR ADMISSION' in testo
    assert 'DOMANDA DI AMMISSIONE' not in testo


@pytest.mark.django_db
def test_contratto_sponsor_in_inglese_per_contratto_en(contratto_en):
    doc = pg.generate_sponsor_contract_pdf(contratto_en)
    assert doc is not None
    docx = [p for p in _docx_generati(contratto_en)
            if 'contratto_sponsor' in p.name.lower()]
    assert docx, 'docx intermedio del contratto sponsor non trovato'
    testo = _docx_text(docx[0])
    assert 'SPONSORSHIP AGREEMENT' in testo
