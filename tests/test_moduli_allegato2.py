"""Moduli PDF (es. ME1/ME2) accodati in fondo all'Allegato 2."""
from pypdf import PdfReader
from weasyprint import HTML

from contracts.services.pdf_generator import _accoda_moduli


class _C:
    contract_number = 'MOD-1'


def _pdf(percorso, pagine, testo):
    html = ''.join(f'<p style="page-break-after:always">{testo} {i}</p>' for i in range(pagine))
    percorso.write_bytes(HTML(string=html).write_pdf())
    return percorso


def test_moduli_in_fondo(tmp_path):
    a2 = _pdf(tmp_path / 'a2.pdf', 3, 'REGOLAMENTO')
    mod = _pdf(tmp_path / 'me.pdf', 2, 'MODULO')
    uscita = _accoda_moduli(a2, mod, tmp_path, _C())
    testi = [p.extract_text() for p in PdfReader(str(uscita)).pages]
    assert len(testi) == 5
    assert 'REGOLAMENTO' in testi[2] and 'MODULO 0' in testi[3] and 'MODULO 1' in testi[4]


def test_senza_moduli_niente_cambia(tmp_path):
    a2 = _pdf(tmp_path / 'a2.pdf', 1, 'REGOLAMENTO')
    assert _accoda_moduli(a2, None, tmp_path, _C()) == a2
