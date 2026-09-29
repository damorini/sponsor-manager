"""Guida in prima pagina del contratto e firma della Segreteria nell'Allegato 2."""
from datetime import date

import pytest
from pypdf import PdfReader
from weasyprint import HTML


def _pdf(pagine, percorso):
    html = "".join(
        f'<div style="page-break-after:always;font-family:Arial;font-size:10pt">{p}</div>'
        for p in pagine)
    HTML(string=f"<html><body>{html}</body></html>").write_pdf(str(percorso))


BLOCCO_ALL2 = ("<p>Data ____________________</p>"
               "<p>Firma della Segreteria Organizzativa<br>VALET S.r.l.</p>"
               "<p>____________________________</p><p>Timbro e firma Sponsor</p>")


@pytest.mark.django_db
def test_guida_e_firma_segreteria(tmp_path, sponsor):
    from contracts.models import Contract, ContractKind, ContractStatus
    from contracts.services.guida_firme import completa_contratto
    from events.models import Event
    ev = Event.objects.create(name={"it": "Ev Guida"}, code="GUI",
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    c = Contract.objects.create(sponsor=sponsor, event=ev, language="it",
                                contract_kind=ContractKind.MAIN,
                                status=ContractStatus.SENT)
    f = tmp_path / "completo.pdf"
    _pdf(["Contratto pagina 1",
          "<p>Bologna, ___________</p><p>Bologna, ___________</p>",   # 2 firme
          "<p>Bologna, ___________</p>",                               # Allegato 1: 1 firma
          "Regolamento",
          BLOCCO_ALL2 + BLOCCO_ALL2,                                   # Allegato 2: 2 firme
          "Modulo ME1 Data ______"], f)
    firme = completa_contratto(f, c, [("contratto", 2), ("allegato1", 1),
                                      ("allegato2", 2), ("moduli", 1)])
    r = PdfReader(str(f))
    assert len(r.pages) == 7                       # + la guida
    guida = r.pages[0].extract_text()
    assert "come completare e restituire il contratto" in guida.lower()
    assert "Invio contratto firmato" in guida
    # pagine del file (la guida e' la 1): contratto 2-3, all.1 4, all.2 5-6, moduli 7
    assert [(x["pagina"], x["n"]) for x in firme] == [(3, 2), (4, 1), (6, 2)]
    assert "5 firme" in guida
    assert "moduli allegati (pagina 7)" in guida
    # firma della Segreteria (immagine) sulla pagina dell'Allegato 2
    assert r.pages[5].images, "firma della Segreteria non apposta"
    assert not r.pages[1].images
