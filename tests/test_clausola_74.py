"""Clausola 7.4 (annullamento dell'evento): rimborso con bonifico entro 90
giorni, in tre capoversi, nei modelli dei contratti IT/EN."""
from pathlib import Path

import pytest
from django.conf import settings
from docx import Document

CARTELLA = Path(settings.BASE_DIR) / 'contracts' / 'templates_pdf'


@pytest.mark.parametrize('nome,chiave,rimborso', [
    ('template_contratto_sponsor_non_ecm_it.docx', 'non potesse aver luogo',
     'bonifico bancario entro 90 gg. successivi alla data di inizio prevista'),
    ('template_non_ecm_it.docx', 'non potesse aver luogo',
     'bonifico bancario entro 90 gg. successivi alla data di inizio prevista'),
    ('template_contratto_sponsor_non_ecm_en.docx', 'cannot take place',
     'bank transfer within 90 days of the scheduled start date'),
    ('template_non_ecm_en.docx', 'be unable to take place',
     'bank transfer within 90 days of the scheduled start date'),
])
def test_clausola_74(nome, chiave, rimborso):
    testi = [p.text.strip() for p in Document(str(CARTELLA / nome)).paragraphs]
    i = next(i for i, t in enumerate(testi) if t.startswith('7.4') and chiave in t)
    assert 'di quando versato' not in testi[i]
    assert rimborso in testi[i + 1]
    assert testi[i + 2] and not testi[i + 2].startswith('7.')
