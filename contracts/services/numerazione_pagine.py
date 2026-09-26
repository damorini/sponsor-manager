"""Numerazione delle pagine del contratto completo, parte per parte:
«CONTRATTO pag. 1 di 5», «ALLEGATO 1 pag. 1 di 3», «ALLEGATO 2 pag. 1 di 4».
Il timbro va in basso a destra, accanto ai dati VALET del piè di pagina."""
import io
import logging

logger = logging.getLogger(__name__)

ETICHETTE = {
    'it': {'contratto': 'CONTRATTO', 'allegato': 'ALLEGATO', 'pag': 'pag. {n} di {tot}'},
    'en': {'contratto': 'AGREEMENT', 'allegato': 'ANNEX', 'pag': 'page {n} of {tot}'},
}


def etichette(pagine_per_parte, lingua='it'):
    """[(titolo, numero pagina)] per ogni pagina, dati i conteggi delle parti
    nell'ordine: contratto, allegato 1, allegato 2..."""
    e = ETICHETTE['en' if lingua == 'en' else 'it']
    out = []
    for i, tot in enumerate(pagine_per_parte):
        titolo = e['contratto'] if i == 0 else f"{e['allegato']} {i}"
        for n in range(1, tot + 1):
            out.append((titolo, e['pag'].format(n=n, tot=tot)))
    return out


def _timbri_pdf(pagine, etich):
    """PDF trasparente con un timbro per pagina (stesse misure delle pagine)."""
    from django.utils.html import escape
    from weasyprint import HTML
    blocchi = []
    for (w, h), (titolo, pag) in zip(pagine, etich):
        blocchi.append(
            f'<div class="p" style="width:{w}pt;height:{h}pt;">'
            f'<div class="n"><b>{escape(titolo)}</b><br>{escape(pag)}</div></div>')
    w0, h0 = pagine[0]
    html = (
        '<html><head><style>'
        f'@page {{ size: {w0}pt {h0}pt; margin: 0; }}'
        'body { margin: 0; }'
        '.p { position: relative; page-break-after: always; overflow: hidden; }'
        '.p:last-child { page-break-after: auto; }'
        '.n { position: absolute; right: 34pt; bottom: 24pt; text-align: right;'
        ' font-family: Arial, Helvetica, sans-serif; font-size: 7pt; line-height: 1.3;'
        ' color: #4b5563; }'
        '</style></head><body>' + ''.join(blocchi) + '</body></html>')
    return HTML(string=html).write_pdf()


def numera(percorso_pdf, pagine_per_parte, lingua='it'):
    """Timbra ogni pagina del PDF (sovrascrive il file). Se i conteggi non
    tornano con le pagine del file, non tocca nulla. Ritorna True se timbrato."""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(percorso_pdf))
    if sum(pagine_per_parte) != len(reader.pages) or not reader.pages:
        logger.warning("Numerazione pagine saltata: %s pagine attese, %s nel file",
                       sum(pagine_per_parte), len(reader.pages))
        return False
    misure = [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]
    timbri = PdfReader(io.BytesIO(_timbri_pdf(misure, etichette(pagine_per_parte, lingua))))
    writer = PdfWriter()
    for pagina, timbro in zip(reader.pages, timbri.pages):
        pagina.merge_page(timbro)
        writer.add_page(pagina)
    with open(percorso_pdf, 'wb') as fh:
        writer.write(fh)
    return True
