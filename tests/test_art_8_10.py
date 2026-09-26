"""Contratto: art. 8-10 spostati dal Regolamento tecnico, vecchi 8-9 ora 11-12,
7.6 e dichiarazione 1341-1342 aggiornati (elenco sulla stessa riga, non in
grassetto)."""
import re
from pathlib import Path

import pytest
from django.conf import settings
from docx import Document

CARTELLA = Path(settings.BASE_DIR) / 'contracts' / 'templates_pdf'


@pytest.mark.parametrize('lingua,titoli,art76', [
    ('it', ['8. Altoparlanti', '9. Azioni promo-pubblicitarie', '10. Riconsegna',
            '11. Modifiche o variazioni', '12. Legge applicabile'],
     'articoli 2, 3, 4, 5, 7, 8, 9, 10, 11, 12'),
    ('en', ['8. Loudspeakers', '9. Promotional', '10. Return of the space',
            '11. Amendments or variations', '12. Governing law'],
     'articles 2, 3, 4, 5, 7, 8, 9, 10, 11 and 12'),
])
def test_articoli_e_riferimenti(lingua, titoli, art76):
    d = Document(str(CARTELLA / f'template_contratto_sponsor_non_ecm_{lingua}.docx'))
    testi = [p.text.strip() for p in d.paragraphs]
    posizioni = [next(i for i, t in enumerate(testi) if t.startswith(x)) for x in titoli]
    assert posizioni == sorted(posizioni)
    for n in ('8.1', '8.2', '9.1', '9.2', '10.1', '10.2', '11.1', '12.1'):
        assert any(t.startswith(n + ' ') for t in testi), n
    assert any(art76 in t for t in testi)
    dich = next(p for p in d.paragraphs if '1341' in p.text and '1342' in p.text)
    assert re.search(r'(relative a:|relating to:) 3\. ', dich.text)
    assert '12. ' in dich.text
    elenco = [r for r in dich.runs if r.text.strip().startswith('3.')]
    assert elenco and not elenco[0].bold
