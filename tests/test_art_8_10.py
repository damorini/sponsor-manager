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
    ('it', ['4. ASSEGNAZIONE DEGLI SPAZI ESPOSITIVI', '5. DURATA',
            '9. ALTOPARLANTI', '10. AZIONI PROMO-PUBBLICITARIE', '11. RICONSEGNA',
            '12. ESONERO DI RESPONSABILITÀ', '13. MODIFICHE O VARIAZIONI',
            '14. LEGGE APPLICABILE'],
     'l’art. 6 dell’Allegato 2'),
    ('en', ['4. ALLOCATION OF EXHIBITION SPACES', '5. TERM AND TERMINATION',
            '9. LOUDSPEAKERS', '10. PROMOTIONAL', '11. RETURN OF THE SPACE',
            '12. EXEMPTION FROM LIABILITY', '13. AMENDMENTS OR VARIATIONS',
            '14. GOVERNING LAW'],
     'Art. 6 of Annex 2 applies'),
])
def test_articoli_e_riferimenti(lingua, titoli, art76):
    d = Document(str(CARTELLA / f'template_contratto_sponsor_non_ecm_{lingua}.docx'))
    testi = [p.text.strip() for p in d.paragraphs]
    posizioni = [next(i for i, t in enumerate(testi) if t.startswith(x)) for x in titoli]
    assert posizioni == sorted(posizioni)
    for n in ('4.1', '4.2', '4.3', '9.1', '9.2', '10.1', '10.2', '10.3', '11.1', '11.2',
              '12.1', '13.1', '14.1'):
        assert any(t.startswith(n + ' ') for t in testi), n
    assert any(art76 in t for t in testi)   # 8.5: rimandi all'art. 6 All. 2 e al 5.3
    dich = next(p for p in d.paragraphs if '1341' in p.text and '1342' in p.text)
    assert re.search(r'(relative a:|relating to:) 3\. ', dich.text)
    assert '4. ' in dich.text and '14. ' in dich.text
    elenco = [r for r in dich.runs if r.text.strip().startswith('3.')]
    assert not elenco or not elenco[0].bold
    # terminologia unica
    testo = ' '.join(testi)
    for vietato in ('Organizzatore', 'Espositore', 'Organiser', 'Exhibitor'):
        assert vietato not in testo, vietato
