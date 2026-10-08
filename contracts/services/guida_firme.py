"""Contratto completo (contratto + Allegato 1 + Allegato 2 + moduli):
- firma della Segreteria Organizzativa (Daniele Morini) sulle righe
  «Firma della Segreteria Organizzativa» dell'Allegato 2;
- prima pagina con la guida: di cosa si compone il documento, in quali pagine
  firmare e come restituirlo dal portale.
Le pagine delle firme si ricavano dal file vero: ogni riga «Bologna, ____» /
«Data ____» e' una firma richiesta allo Sponsor."""
import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

FIRMA_SEGRETERIA = Path(__file__).resolve().parent.parent / 'templates_pdf' / 'firma_segreteria.png'

# Riga della data sotto ogni blocco firma, da sola sulla riga: «Data ______»,
# «Bologna, ______» oppure con la data gia' stampata «Bologna, 05/10/2026»
# (contratto e Domanda la stampano: prima quelle firme sfuggivano alla guida).
_RIGA_DATA = re.compile(
    r'^\s*(?:Data|Date|[A-ZÀ-Ý][a-zà-ÿ]+(?: [A-ZÀ-Ý][a-zà-ÿ]+)*,)'
    r'\s*(?:_{3,}|\d{1,2}/\d{1,2}/\d{2,4})\s*$', re.M)
# Etichetta della firma della Segreteria nell'Allegato 2
_ETICHETTA_SEGRETERIA = re.compile(
    r'Firma della Segreteria Organizzativa|Organi[sz]ing Secretariat', re.I)

TITOLI = {
    'it': {
        'contratto': 'Contratto fra le parti',
        'allegato1': 'Allegato 1 – Domanda di ammissione',
        'allegato2': 'Allegato 2 – Regolamento tecnico',
        'moduli': 'Moduli per il montaggio da parte di allestitori esterni',
    },
    'en': {
        'contratto': 'Agreement between the parties',
        'allegato1': 'Annex 1 – Admission request',
        'allegato2': 'Annex 2 – Technical regulations',
        'moduli': 'Forms for set-up by external stand builders',
    },
}


def firme_per_pagina(reader, prima, ultima):
    """[(indice pagina 0-based, numero firme)] per le pagine prima..ultima
    (0-based, inclusa) che chiedono firme."""
    out = []
    for i in range(prima, ultima + 1):
        try:
            testo = reader.pages[i].extract_text() or ''
        except Exception:
            continue
        n = len(_RIGA_DATA.findall(testo))
        if n:
            out.append((i, n))
    return out


def _posizioni_firma_segreteria(pagina):
    """Punti (x, y) delle righe ____ sotto ogni «Firma della Segreteria
    Organizzativa» della pagina (coordinate PDF, origine in basso)."""
    etichette, linee = [], []

    def visita(testo, cm, tm, _fd, _fs):
        t = (testo or '').strip()
        if not t:
            return
        # posizione sulla pagina: matrice del testo per quella della pagina
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if _ETICHETTA_SEGRETERIA.search(t):
            etichette.append((x, y))
        elif re.fullmatch(r'_{8,}', t):
            linee.append((x, y))

    pagina.extract_text(visitor_text=visita)
    punti = []
    for ex, ey in etichette:
        sotto = [(lx, ly) for lx, ly in linee
                 if abs(lx - ex) < 15 and 0 < ey - ly < 60]
        if sotto:
            punti.append(max(sotto, key=lambda p: p[1]))
    return punti


def _sovrapposizione(misure, firme_per_pag):
    """PDF trasparente, una pagina per ogni pagina da timbrare, con la firma
    sopra ciascuna riga."""
    from weasyprint import HTML
    blocchi = []
    for (w, h), punti in zip(misure, firme_per_pag):
        imgs = ''.join(
            f'<img src="{FIRMA_SEGRETERIA.as_uri()}" style="position:absolute;'
            f'left:{x + 62:.1f}pt;top:{h - y - 30:.1f}pt;height:32pt;">'
            for x, y in punti)
        blocchi.append(f'<div class="p" style="width:{w}pt;height:{h}pt;">{imgs}</div>')
    w0, h0 = misure[0]
    html = (
        '<html><head><style>'
        f'@page {{ size: {w0}pt {h0}pt; margin: 0; }} body {{ margin: 0; }}'
        '.p { position: relative; page-break-after: always; overflow: hidden; }'
        '.p:last-child { page-break-after: auto; }'
        '</style></head><body>' + ''.join(blocchi) + '</body></html>')
    return HTML(string=html).write_pdf()


def firma_segreteria_allegato(percorso_pdf, prima, ultima):
    """Mette la firma della Segreteria Organizzativa sulle righe «Firma della
    Segreteria Organizzativa» delle pagine prima..ultima (0-based). Ritorna il
    numero di firme apposte."""
    from pypdf import PdfReader, PdfWriter
    if not FIRMA_SEGRETERIA.exists():
        return 0
    reader = PdfReader(str(percorso_pdf))
    da_timbrare = {}
    for i in range(prima, min(ultima, len(reader.pages) - 1) + 1):
        punti = _posizioni_firma_segreteria(reader.pages[i])
        if punti:
            da_timbrare[i] = punti
    if not da_timbrare:
        return 0
    indici = sorted(da_timbrare)
    misure = [(float(reader.pages[i].mediabox.width),
               float(reader.pages[i].mediabox.height)) for i in indici]
    sopra = PdfReader(io.BytesIO(_sovrapposizione(misure, [da_timbrare[i] for i in indici])))
    for i, pagina_firma in zip(indici, sopra.pages):
        reader.pages[i].merge_page(pagina_firma)
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    with open(percorso_pdf, 'wb') as fh:
        writer.write(fh)
    return sum(len(v) for v in da_timbrare.values())


def _intervalli(parti):
    """[(chiave, prima, ultima)] 0-based dalle parti [(chiave, pagine)]."""
    out, inizio = [], 0
    for chiave, n in parti:
        if n:
            out.append((chiave, inizio, inizio + n - 1))
            inizio += n
    return out


def _copertina_pdf(contract, voci, firme, moduli, lingua):
    from django.conf import settings
    from django.template.loader import render_to_string
    from weasyprint import HTML
    evento = contract.event
    try:
        nome_evento = evento.get_name(lingua)
    except Exception:
        nome_evento = str(evento)
    html = render_to_string('contract_cover.html', {
        'en': lingua == 'en',
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': evento,
        'event_name': nome_evento,
        'voci': voci,
        'firme': firme,
        'totale_firme': sum(f['n'] for f in firme),
        'moduli': moduli,
        'brand_color': getattr(settings, 'BRAND_PRIMARY_COLOR', '#1d6534'),
    })
    return HTML(string=html).write_pdf()


def completa_contratto(percorso_pdf, contract, parti):
    """Firma della Segreteria nell'Allegato 2 e guida in prima pagina.
    parti: [(chiave, numero pagine)] nell'ordine del file, chiavi fra
    'contratto', 'allegato1', 'allegato2', 'moduli'."""
    from pypdf import PdfReader, PdfWriter
    lingua = 'en' if (contract.language or 'it') == 'en' else 'it'
    intervalli = _intervalli(parti)

    for chiave, prima, ultima in intervalli:
        if chiave == 'allegato2':
            firma_segreteria_allegato(percorso_pdf, prima, ultima)

    reader = PdfReader(str(percorso_pdf))
    # il timbro «ALLEGATO 2 pag. x di N» conta anche i moduli accodati
    pagine_moduli = sum(n for k, n in parti if k == 'moduli')
    # +1: la guida diventa la pagina 1 del file
    voci, firme, moduli = [], [], None
    for chiave, prima, ultima in intervalli:
        voce = {'titolo': TITOLI[lingua][chiave], 'dal': prima + 2, 'al': ultima + 2}
        voci.append(voce)
        if chiave == 'moduli':
            moduli = voce
            continue
        for i, n in firme_per_pagina(reader, prima, ultima):
            firme.append({'pagina': i + 2, 'n': n, 'parte': TITOLI[lingua][chiave],
                          'pag_parte': i - prima + 1,
                          'tot_parte': ultima - prima + 1
                          + (pagine_moduli if chiave == 'allegato2' else 0)})

    copertina = PdfReader(io.BytesIO(_copertina_pdf(contract, voci, firme, moduli, lingua)))
    writer = PdfWriter()
    for p in copertina.pages:
        writer.add_page(p)
    for p in reader.pages:
        writer.add_page(p)
    with open(percorso_pdf, 'wb') as fh:
        writer.write(fh)
    return firme
