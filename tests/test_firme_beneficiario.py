"""Domanda: beneficiario del bonifico = titolare del conto VALET.
Contratto: «Bologna, data» prima di entrambe le firme."""
from pathlib import Path

import pytest
from django.conf import settings
from docx import Document

CARTELLA = Path(settings.BASE_DIR) / 'contracts' / 'templates_pdf'


@pytest.mark.parametrize('organizzatore,atteso', [
    ('Valet Srl', 'VALET Società a Responsabilità Limitata'),
    ('VALET SRL', 'VALET Società a Responsabilità Limitata'),
    ('', 'VALET Società a Responsabilità Limitata'),
    ('ACME CONGRESSI S.P.A.', 'ACME CONGRESSI S.P.A.'),
])
def test_beneficiario(organizzatore, atteso):
    from contracts.services.pdf_generator import _beneficiario_bonifico
    assert _beneficiario_bonifico(organizzatore) == atteso


@pytest.mark.parametrize('lingua', ['it', 'en'])
def test_luogo_e_data_prima_di_ogni_firma(lingua):
    d = Document(str(CARTELLA / f'template_contratto_sponsor_non_ecm_{lingua}.docx'))
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    for tb in d.tables[-2:]:
        el, testi = tb._tbl.getprevious(), []
        for _ in range(3):
            testi.append(''.join(t.text or '' for t in el.iter(W + 't')))
            el = el.getprevious()
        assert any(t.strip().startswith('Bologna,') for t in testi), testi
