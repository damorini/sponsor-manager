"""Numerazione pagine del contratto completo, parte per parte."""
from pypdf import PdfReader
from weasyprint import HTML

from contracts.services.numerazione_pagine import etichette, numera


def test_etichette_per_parte():
    e = etichette([2, 1, 2])
    assert e == [('CONTRATTO', 'pag. 1 di 2'), ('CONTRATTO', 'pag. 2 di 2'),
                 ('ALLEGATO 1', 'pag. 1 di 1'),
                 ('ALLEGATO 2', 'pag. 1 di 2'), ('ALLEGATO 2', 'pag. 2 di 2')]
    assert etichette([1, 1], 'en') == [('AGREEMENT', 'page 1 of 1'), ('ANNEX 1', 'page 1 of 1')]


def test_timbro_su_ogni_pagina(tmp_path):
    html = ('<style>@page{size:A4}</style>' +
            '<p style="page-break-after:always">testo</p>' * 4 + '<p>fine</p>')
    pdf = tmp_path / 'c.pdf'
    pdf.write_bytes(HTML(string=html).write_pdf())
    assert numera(pdf, [2, 1, 2])
    testi = [p.extract_text() for p in PdfReader(str(pdf)).pages]
    assert len(testi) == 5
    assert 'CONTRATTO' in testi[0] and 'pag. 1 di 2' in testi[0]
    assert 'ALLEGATO 1' in testi[2] and 'pag. 1 di 1' in testi[2]
    assert 'ALLEGATO 2' in testi[4] and 'pag. 2 di 2' in testi[4]
    assert 'testo' in testi[0] or 'fine' in testi[4]


def test_conteggi_sbagliati_non_tocca(tmp_path):
    pdf = tmp_path / 'c.pdf'
    pdf.write_bytes(HTML(string='<p>uno</p>').write_pdf())
    prima = pdf.read_bytes()
    assert not numera(pdf, [2, 1])
    assert pdf.read_bytes() == prima
