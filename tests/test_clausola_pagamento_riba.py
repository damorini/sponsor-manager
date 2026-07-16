"""Regressione: la clausola SALDO del contratto/domanda di ammissione segue
il metodo di pagamento impostato sul contratto. Di default (o Bonifico
generico) resta 'valuta fissa alla scadenza saldo'; con RI.BA. riporta i
termini liberi (es. '60 gg F.M.') invece della data fissa; con Bonifico
(B.B.) a scadenza fissa usa la dicitura 'PAGAMENTO: ... tramite B.B. con
scadenza [giorno] [mese] [anno]' al posto di 'SALDO'."""
from datetime import date
from decimal import Decimal

import pytest

from catalog.models import Service
from contracts.models import Contract, ContractKind, ContractLine, ContractStatus, PaymentMethod
from contracts.services.pdf_generator import generate_admission_request_pdf
from events.models import Event, EventType
from sponsors.models import Contact


@pytest.fixture
def contratto_riba(db, sponsor, dati_firmatario_completi):
    Contact.objects.create(
        sponsor=sponsor, full_name='Firmatario Test', email='firmatario@test.it',
        is_signer=True, **dati_firmatario_completi,
    )
    event = Event.objects.create(
        name={'it': 'Evento RIBA', 'en': 'RIBA Event'}, code='RB',
        event_type=EventType.NON_ECM,
        start_date=date(2026, 12, 1), end_date=date(2026, 12, 2),
    )
    contract = Contract.objects.create(
        sponsor=sponsor, event=event, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number='RB-26-001',
        balance_due_date_override=date(2026, 10, 29),
    )
    service = Service.objects.create(
        event=event, code='SRV1', name={'it': 'Servizio', 'en': 'Service'},
        base_price=Decimal('1000'), vat_rate=Decimal('22'),
    )
    ContractLine.objects.create(
        contract=contract, service=service, quantity=1,
        unit_price=Decimal('1000'), vat_rate=Decimal('22'),
    )
    contract.total = Decimal('1220.00')
    contract.save(update_fields=['total'])
    return contract


def test_clausola_default_valuta_fissa(contratto_riba):
    testo = contratto_riba.payment_clause_text
    assert 'valuta fissa al 29/10/2026' in testo
    assert 'Ri.Ba.' not in testo


def test_clausola_riba_usa_termini_liberi(contratto_riba):
    contratto_riba.payment_method = PaymentMethod.RIBA
    contratto_riba.payment_terms = '60 gg F.M.'
    contratto_riba.save(update_fields=['payment_method', 'payment_terms'])
    testo = contratto_riba.payment_clause_text
    assert 'Ri.Ba. 60 gg F.M.' in testo
    assert 'valuta fissa' not in testo
    assert '29/10/2026' not in testo


def test_clausola_bonifico_scadenza_fissa_dicitura_bb(contratto_riba):
    contratto_riba.payment_method = PaymentMethod.BANK_TRANSFER_FIXED_DATE
    contratto_riba.save(update_fields=['payment_method'])
    testo = contratto_riba.payment_clause_text
    assert testo == 'PAGAMENTO: € 1.220,00 tramite B.B. con scadenza 29 OTTOBRE 2026.'
    assert 'SALDO' not in testo


def test_clausola_bank_transfer_generico_resta_invariata(contratto_riba):
    """Il valore storico 'bank_transfer' (gia' presente su contratti
    esistenti per default) NON deve attivare la nuova dicitura: solo il
    valore dedicato 'bb_scadenza_fissa' lo fa."""
    contratto_riba.payment_method = PaymentMethod.BANK_TRANSFER
    contratto_riba.save(update_fields=['payment_method'])
    testo = contratto_riba.payment_clause_text
    assert 'valuta fissa al 29/10/2026' in testo
    assert 'PAGAMENTO' not in testo


@pytest.mark.django_db
def test_pdf_domanda_riporta_clausola_riba(contratto_riba):
    contratto_riba.payment_method = PaymentMethod.RIBA
    contratto_riba.payment_terms = '60 gg F.M.'
    contratto_riba.save(update_fields=['payment_method', 'payment_terms'])

    doc = generate_admission_request_pdf(contratto_riba)
    assert doc is not None
    assert doc.mime_type == 'application/pdf'

    from pypdf import PdfReader
    from pathlib import Path
    from django.conf import settings
    rel = doc.storage_url.replace(settings.MEDIA_URL, '', 1)
    reader = PdfReader(str(Path(settings.MEDIA_ROOT) / rel))
    testo = ' '.join((p.extract_text() or '') for p in reader.pages)
    assert 'Ri.Ba.' in testo
    assert '60 gg F.M.' in testo
    assert 'valuta fissa' not in testo
