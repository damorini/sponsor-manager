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
    ('it', ['4. Assegnazione degli spazi espositivi', '5. Durata',
            '9. Altoparlanti', '10. Azioni promo-pubblicitarie', '11. Riconsegna',
            '12. Esonero di responsabilità', '13. Modifiche o variazioni',
            '14. Legge applicabile'],
     'articoli 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14'),
    ('en', ['4. Allocation of exhibition spaces', '5. Term and Termination',
            '9. Loudspeakers', '10. Promotional', '11. Return of the space',
            '12. Exemption from liability', '13. Amendments or variations',
            '14. Governing law'],
     'articles 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13 and 14'),
])
def test_articoli_e_riferimenti(lingua, titoli, art76):
    d = Document(str(CARTELLA / f'template_contratto_sponsor_non_ecm_{lingua}.docx'))
    testi = [p.text.strip() for p in d.paragraphs]
    posizioni = [next(i for i, t in enumerate(testi) if t.startswith(x)) for x in titoli]
    assert posizioni == sorted(posizioni)
    for n in ('4.1', '4.2', '4.3', '9.1', '9.2', '10.1', '10.2', '10.3', '11.1', '11.2',
              '12.1', '13.1', '14.1'):
        assert any(t.startswith(n + ' ') for t in testi), n
    assert any(art76 in t for t in testi)
    dich = next(p for p in d.paragraphs if '1341' in p.text and '1342' in p.text)
    assert re.search(r'(relative a:|relating to:) 3\. ', dich.text)
    assert '4. ' in dich.text and '14. ' in dich.text
    elenco = [r for r in dich.runs if r.text.strip().startswith('3.')]
    assert not elenco or not elenco[0].bold
    # terminologia unica
    testo = ' '.join(testi)
    for vietato in ('Organizzatore', 'Espositore', 'Organiser', 'Exhibitor'):
        assert vietato not in testo, vietato
