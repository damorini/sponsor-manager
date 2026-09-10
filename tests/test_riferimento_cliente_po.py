"""Riferimento del cliente (numero d'ordine / PO) sui documenti.

Se il campo e' compilato deve comparire su preventivo, contratto (ECM e
non-ECM) e domanda di ammissione; se e' vuoto non deve comparire NULLA:
nessuna etichetta orfana, nessuna riga vuota.
"""
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.conf import settings

from contracts.models import Contract
from events.models import Event

TEMPLATES = Path(settings.BASE_DIR) / 'contracts' / 'templates_pdf'

DOCX_ATTESI = [
    ('template_contratto_sponsor_non_ecm_it.docx', 'Vostro riferimento'),
    ('template_contratto_sponsor_non_ecm_en.docx', 'Your reference'),
    ('template_ecm_it.docx', 'Vostro riferimento'),
    ('template_ecm_en.docx', 'Your reference'),
    ('template_domanda_ammissione_it.docx', 'Vostro riferimento'),
    ('template_domanda_ammissione_en.docx', 'Your reference'),
]


def _testo_docx(path):
    from docx import Document as Docx
    d = Docx(str(path))
    parti = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parti.extend(c.text for c in row.cells)
    return '\n'.join(parti)


def _rendi(nome, riferimento):
    """Renderizza il template docxtpl con un contratto finto e ritorna il testo."""
    import tempfile

    from docxtpl import DocxTemplate

    from contracts.services.pdf_generator import get_jinja_env

    class Finto(dict):
        __getattr__ = dict.get

    contesto = {
        'contract': Finto(customer_reference=riferimento, deposit_amount=0),
        'sponsor': Finto(), 'signer': Finto(), 'event': Finto(),
        'contact_referente': Finto(),
        'organizer_name': 'VALET SRL', 'operational_email': 'x@y.it',
        'as_allegato': False, 'has_deposit': False, 'stand_notes': '',
        'deposit_percent': 0, 'lines': [], 'lines_by_category': [],
        'services_list': [], 'stand_size': '', 'signature_place': 'Bologna',
        'imponibile': '0,00', 'iva': '0,00', 'totale': '0,00',
        'aliquota_iva': '22%', 'cancellation_penalty_percent': 50,
        'penale_percent': 50, 'deposit_amount': '0,00',
        'balance_amount': '0,00', 'deposit_due_date': '',
        'balance_due_date': '', 'payment_terms': '',
    }
    doc = DocxTemplate(str(TEMPLATES / nome))
    doc.render(contesto, jinja_env=get_jinja_env())
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        doc.save(f.name)
        return _testo_docx(f.name)


@pytest.mark.parametrize('nome,etichetta', DOCX_ATTESI)
def test_docx_stampa_il_riferimento_quando_compilato(nome, etichetta):
    testo = _rendi(nome, 'PO-2026-4471')
    assert etichetta in testo, f'{nome}: etichetta mancante'
    assert 'PO-2026-4471' in testo, f'{nome}: riferimento non stampato'


@pytest.mark.parametrize('nome,etichetta', DOCX_ATTESI)
def test_docx_non_stampa_nulla_quando_vuoto(nome, etichetta):
    testo = _rendi(nome, '')
    assert etichetta not in testo, f'{nome}: etichetta orfana con campo vuoto'


@pytest.fixture
def contratto_po(db, sponsor):
    inizio = date.today() + timedelta(days=60)
    ev = Event.objects.create(name={'it': 'Evento PO', 'en': 'PO Event'},
                              code='PO', start_date=inizio,
                              end_date=inizio + timedelta(days=1))
    return Contract.objects.create(sponsor=sponsor, event=ev,
                                   contract_number='PO-26-001',
                                   customer_reference='PO-2026-4471')


@pytest.mark.django_db
def test_preventivo_html_mostra_il_riferimento(contratto_po):
    from django.template.loader import render_to_string
    html = render_to_string('quote_pdf.html', {
        'contract': contratto_po, 'sponsor': contratto_po.sponsor,
        'event': contratto_po.event, 'lines': [],
        't': {'your_ref': 'Vostro riferimento'}, 'org': {}, 'sci': None,
    })
    assert 'Vostro riferimento' in html
    assert 'PO-2026-4471' in html


@pytest.mark.django_db
def test_preventivo_html_senza_riferimento_non_mostra_etichetta(contratto_po):
    from django.template.loader import render_to_string
    contratto_po.customer_reference = ''
    contratto_po.save()
    html = render_to_string('quote_pdf.html', {
        'contract': contratto_po, 'sponsor': contratto_po.sponsor,
        'event': contratto_po.event, 'lines': [],
        't': {'your_ref': 'Vostro riferimento'}, 'org': {}, 'sci': None,
    })
    assert 'Vostro riferimento' not in html


@pytest.mark.django_db
def test_campo_e_opzionale(db, sponsor):
    """Un contratto senza riferimento resta perfettamente valido."""
    inizio = date.today() + timedelta(days=60)
    ev = Event.objects.create(name={'it': 'Evento PO2'}, code='PO2',
                              start_date=inizio, end_date=inizio + timedelta(days=1))
    c = Contract.objects.create(sponsor=sponsor, event=ev,
                                contract_number='PO2-26-001')
    c.full_clean(exclude=['contract_number'])
    assert c.customer_reference == ''
