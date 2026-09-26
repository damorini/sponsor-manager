"""
ALLEGATO 2 del contratto di sponsorizzazione (es. Regolamento tecnico).

L'operatore carica sull'evento un Word con i soli TESTI. A ogni contratto il
sistema ne prepara una copia personalizzata:
  - segnaposto facoltativi nel Word ({{ azienda }}, {{ stand }},
    {{ contratto }}, {{ evento }}, {{ date_evento }}, {{ sede }}) compilati;
  - titolo «ALLEGATO 2 – <titolo>» se il Word non lo ha gia';
  - in prima pagina il riquadro Azienda / Stand / Contratto n.;
  - la tabella «Attivita' | Data | Orario» riempita coi giorni di
    allestimento/disallestimento dell'evento;
  - stile uniformato al contratto (Arial 9, giustificato, titoli in nero);
  - intestazione e pie' di pagina del contratto (dati dell'evento), al posto
    di quelli eventualmente presenti nel Word.
"""
import copy
import logging

logger = logging.getLogger(__name__)

FONT = 'Arial'
# Allegato 2 un punto sotto il contratto (9): stile 'clausole di polizza'.
CORPO = 8
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _etichetta_stand(contract):
    stand = getattr(contract, 'stand', None)
    if stand:
        return stand.code
    blocco = getattr(contract, 'stand_block', None)
    return blocco.code if blocco else '-'


def _porta_accesso(contract):
    """Porta di accesso dello stand; per un blocco, la prima indicata sui
    suoi stand."""
    stand = getattr(contract, 'stand', None)
    if stand:
        return (stand.access_door or '').strip()
    blocco = getattr(contract, 'stand_block', None)
    if blocco:
        for s in blocco.stands.exclude(access_door='').order_by('code'):
            return s.access_door.strip()
    return ''


def _date_evento(event):
    inizio, fine = event.start_date, event.end_date
    if not inizio:
        return ''
    if not fine or fine == inizio:
        return inizio.strftime('%d/%m/%Y')
    return f"{inizio:%d/%m/%Y} – {fine:%d/%m/%Y}"


def contesto(contract):
    from contracts.services.pdf_generator import _event_for_template
    ev = _event_for_template(contract.event)
    return {
        'azienda': contract.sponsor.legal_name,
        'stand': _etichetta_stand(contract),
        'contratto': contract.contract_number or '',
        'evento': ev.name,
        'date_evento': _date_evento(contract.event),
        'sede': ev.location,
        'accesso': _porta_accesso(contract),
        'montaggio_indirizzo': _testo_a_righe(
            getattr(contract.event, 'montaggio_indirizzo', '')) or 'da comunicare',
        'montaggio_dettagli': _testo_a_righe(
            getattr(contract.event, 'montaggio_dettagli', '')),
        **_disallestimento(contract.event),
        'magazzino_ritiro': _testo_a_righe(getattr(contract.event, 'magazzino_ritiro', '')),
        'regole_montaggio': _testo_a_righe(getattr(contract.event, 'regole_montaggio', '')),
        'magazzino_indirizzo': _testo_a_righe(
            getattr(contract.event, 'magazzino_indirizzo', '')) or 'da comunicare',
        'magazzino_dettagli': _testo_a_righe(
            getattr(contract.event, 'magazzino_dettagli', '')),
    }


MESI = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio',
        'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']


def _disallestimento(event):
    """Orari e giorno di disallestimento dalla tabella dell'evento: inizio del
    primo giorno, fine e data dell'ultimo («27 febbraio 2027»)."""
    giorni = []
    if hasattr(event, 'setup_days'):
        giorni = list(event.setup_days.filter(kind='disallestimento')
                      .order_by('date', 'start_time'))
    if not giorni:
        return {'disallestimento_inizio': 'da comunicare',
                'disallestimento_fine': 'da comunicare',
                'disallestimento_giorno': 'giorno da comunicare'}
    primo, ultimo = giorni[0], giorni[-1]
    return {
        'disallestimento_inizio': f"{primo.start_time:%H:%M}",
        'disallestimento_fine': f"{ultimo.end_time:%H:%M}",
        'disallestimento_giorno': (f"{ultimo.date.day} {MESI[ultimo.date.month - 1]} "
                                   f"{ultimo.date.year}"),
    }


def _testo_a_righe(testo):
    """Testo su piu' righe per docxtpl: Listing mantiene gli a capo."""
    testo = (testo or '').strip()
    if not testo:
        return ''
    from docxtpl import Listing
    return Listing(testo)


def _compila_segnaposto(percorso, ctx):
    """Render docxtpl dei segnaposto; se il Word non ne ha (o ha graffe
    'strane') il file resta com'e'."""
    try:
        from docxtpl import DocxTemplate
        doc = DocxTemplate(str(percorso))
        doc.render(ctx)
        doc.save(str(percorso))
    except Exception as e:
        logger.warning("Allegato 2: segnaposto non compilati (%s)", e)


def _stile_run(run, size=9, bold=None):
    run.font.name = FONT
    rpr = run._r.get_or_add_rPr()
    fonts = rpr.find(W + 'rFonts')
    if fonts is not None:
        for attr in ('ascii', 'hAnsi', 'cs', 'eastAsia'):
            fonts.set(W + attr, FONT)
    from docx.shared import Pt, RGBColor
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.font.bold = bold


def _uniforma_stile(d):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for nome in ('Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2',
                 'Heading 3', 'List Bullet'):
        try:
            st = d.styles[nome]
        except KeyError:
            continue
        st.font.name = FONT
        from docx.shared import RGBColor
        st.font.color.rgb = RGBColor(0, 0, 0)

    def _paragrafo(p):
        stile = p.style.name if p.style is not None else ''
        from docx.shared import Pt
        pf = p.paragraph_format
        if stile == 'Title':
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                _stile_run(r, 12, True)
        elif stile == 'Subtitle':
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                _stile_run(r, 10, True)
                r.font.italic = False
        elif stile.startswith('Heading'):
            pf.space_before, pf.space_after = Pt(5), Pt(1)
            pf.keep_with_next = True
            for r in p.runs:
                _stile_run(r, CORPO, True)
        else:
            if p.alignment is None or p.alignment == WD_ALIGN_PARAGRAPH.LEFT:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            # spaziature strette: il testo e' fitto come in una polizza
            pf.space_before, pf.space_after = Pt(0), Pt(2)
            pf.line_spacing = 1.0
            for r in p.runs:
                _stile_run(r, CORPO)

    for p in d.paragraphs:
        _paragrafo(p)
    for t in d.tables:
        for n, riga in enumerate(t.rows):
            for cella in riga.cells:
                for p in cella.paragraphs:
                    for r in p.runs:
                        # prima riga = intestazione: in grassetto
                        _stile_run(r, CORPO, True if n == 0 and len(t.rows) > 1 else None)


def _titolo(d, contract, titolo):
    """«ALLEGATO 2 – titolo» in testa, solo se il Word non lo dice gia'."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    inizio = ' '.join(p.text for p in d.paragraphs[:4]).upper()
    if 'ALLEGATO 2' in inizio or 'ANNEX 2' in inizio:
        return
    etichetta = 'ANNEX 2' if (contract.language or 'it') == 'en' else 'ALLEGATO 2'
    primo = d.paragraphs[0] if d.paragraphs else d.add_paragraph()
    intest = primo.insert_paragraph_before()
    intest.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _stile_run(intest.add_run(f"{etichetta} – {titolo}" if titolo else etichetta), 14, True)


def _riquadro_dati(d, contract, ctx):
    """Azienda / Stand / Contratto n. subito sotto il titolo del documento."""
    from docx.shared import Pt
    en = (contract.language or 'it') == 'en'
    righe = [('Sponsor', ctx['azienda']),
             ('Stand no.' if en else 'Stand n.', ctx['stand']),
             ('Contract no.' if en else 'Contratto n.', ctx['contratto'])]
    if ctx.get('accesso'):
        righe.append(('Hall access no.' if en else 'Accesso al padiglione n°',
                      ctx['accesso']))
    # ultimo paragrafo "di titolo" nelle prime righe (Title/Subtitle/ALLEGATO)
    dopo = None
    for p in d.paragraphs[:5]:
        nome = p.style.name if p.style is not None else ''
        testo = p.text.strip().upper()
        if nome in ('Title', 'Subtitle') or testo.startswith(('ALLEGATO', 'ANNEX')):
            dopo = p
        elif testo:
            break
    if dopo is None:
        dopo = d.paragraphs[0]
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    def _nuovo_dopo(par):
        el = OxmlElement('w:p')
        par._p.addnext(el)
        return Paragraph(el, par._parent)

    ultimo = _nuovo_dopo(dopo)                  # riga vuota di stacco
    # Azienda su una riga; Stand / Contratto / Accesso in una tabellina a una
    # riga, una casella per voce
    azienda, *voci = righe
    p = _nuovo_dopo(ultimo)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    _stile_run(p.add_run(f"{azienda[0]}: "), 10, True)
    _stile_run(p.add_run(str(azienda[1] or '-')), 10, False)
    tabella = _tabellina_voci(d, voci)
    p._p.addnext(tabella)
    ultimo_el = tabella
    from contracts.services import caratteristiche_spazio as cs
    en = (contract.language or 'it') == 'en'
    for scheda in cs.schede(contract, con_accesso=False):
        el = OxmlElement('w:p')                  # piccolo stacco sopra la tabellina
        ultimo_el.addnext(el)
        sp = Paragraph(el, dopo._parent)
        sp.paragraph_format.space_before = Pt(0)
        sp.paragraph_format.space_after = Pt(0)
        _stile_run(sp.add_run(''), 4, False)
        tbl = cs.tabella_docx(d, scheda, en, cs.larghezza_utile(d), size=9, font=FONT)
        el.addnext(tbl)
        ultimo_el = cs.paragrafi_indicazioni(d, tbl, scheda, en, size=9, font=FONT,
                                             larghezza=cs.larghezza_utile(d))
    stacco = OxmlElement('w:p')
    ultimo_el.addnext(stacco)
    return Paragraph(stacco, dopo._parent)       # riga vuota di stacco


def _tabellina_voci(d, voci):
    """Tabella a una riga (bordi sottili, tutta larghezza) con una casella per
    voce: «Stand n.: 1-A | Contratto n.: ... | Accesso al padiglione n°: 3»."""
    from docx.oxml import OxmlElement
    from docx.shared import Pt
    t = d.add_table(rows=1, cols=len(voci))
    tbl = t._tbl
    tbl.getparent().remove(tbl)                 # la posiziona il chiamante
    tblpr = tbl.tblPr
    bordi = OxmlElement('w:tblBorders')
    for lato in ('top', 'left', 'bottom', 'right', 'insideV'):
        b = OxmlElement(f'w:{lato}')
        b.set(W + 'val', 'single')
        b.set(W + 'sz', '4')
        b.set(W + 'color', '808080')
        bordi.append(b)
    tblpr.append(bordi)
    sp = d.element.body.find(W + 'sectPr')
    pgsz, pgmar = sp.find(W + 'pgSz'), sp.find(W + 'pgMar')
    utile = (int(pgsz.get(W + 'w')) - int(pgmar.get(W + 'left'))
             - int(pgmar.get(W + 'right')))
    for vecchio in tblpr.findall(W + 'tblW'):
        tblpr.remove(vecchio)
    tblw = OxmlElement('w:tblW')
    tblw.set(W + 'w', str(utile))
    tblw.set(W + 'type', 'dxa')
    tblpr.append(tblw)
    for gc in tbl.find(W + 'tblGrid').findall(W + 'gridCol'):
        gc.set(W + 'w', str(utile // len(voci)))
    for cella, (etichetta, valore) in zip(t.rows[0].cells, voci):
        par = cella.paragraphs[0]
        par.paragraph_format.space_before = Pt(2)
        par.paragraph_format.space_after = Pt(2)
        _stile_run(par.add_run(f"{etichetta}: "), 10, True)
        _stile_run(par.add_run(str(valore or '-')), 10, False)
    return tbl


GIORNI = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
DAYS_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _tabella_orari(d, contract):
    """Riempie la tabella «Attivita' | Data | Orario» coi giorni dell'evento."""
    en = (contract.language or 'it') == 'en'
    giorni = list(contract.event.setup_days.all()) if hasattr(
        contract.event, 'setup_days') else []
    for t in d.tables:
        intest = ' '.join(c.text.strip().lower() for c in t.rows[0].cells)
        if not ('data' in intest or 'date' in intest) or not (
                'orario' in intest or 'time' in intest):
            continue
        if len(t.rows) < 2 or len(t.columns) < 3:
            continue
        modello = copy.deepcopy(t.rows[1]._tr)
        for riga in list(t.rows[1:]):
            t._tbl.remove(riga._tr)
        voci = giorni or [None]
        for g in voci:
            tr = copy.deepcopy(modello)
            t._tbl.append(tr)
            from docx.table import _Row
            riga = _Row(tr, t)
            if g is None:
                testi = ['-', 'Da definire' if not en else 'To be defined', '-']
            else:
                nome = (DAYS_EN if en else GIORNI)[g.date.weekday()]
                tipo = g.get_kind_display()
                if en:
                    tipo = 'Set-up' if g.kind == 'allestimento' else 'Dismantling'
                testi = [tipo, f"{nome} {g.date:%d/%m/%Y}",
                         f"{g.start_time:%H:%M} – {g.end_time:%H:%M}"]
            for cella, testo in zip(riga.cells, testi):
                ps = cella.paragraphs
                for extra in ps[1:]:
                    extra._p.getparent().remove(extra._p)
                p = ps[0]
                for r in list(p.runs):
                    r._r.getparent().remove(r._r)
                _stile_run(p.add_run(testo), CORPO)
            if g is not None and (g.notes or '').strip():
                # la nota vale per QUESTO giorno: stesso fondo della riga sopra,
                # nessuna linea fra le due, e il giorno ripetuto nell'etichetta
                _evidenzia_riga(tr, fondo=True, bordo_sotto=False)
                etichetta = (f"Note for {nome} {g.date:%d/%m/%Y}: " if en else
                             f"↳ Nota per {nome.lower()} {g.date:%d/%m/%Y}: ")
                _riga_nota(t, modello, etichetta, g.notes.strip())
        _frase_accesso(t, contract)
        _adatta_a_colonna(d, t, [0.30, 0.40, 0.30])
        return True
    return False


SPAZIO_COLONNE = 284                            # twip (0,5 cm)


def _larghezza_colonna(d):
    """Larghezza di una delle due colonne, in twip."""
    sp = d.element.body.find(W + 'sectPr')
    pgsz, pgmar = sp.find(W + 'pgSz'), sp.find(W + 'pgMar')
    utile = (int(pgsz.get(W + 'w')) - int(pgmar.get(W + 'left'))
             - int(pgmar.get(W + 'right')))
    return (utile - SPAZIO_COLONNE) // 2


def _adatta_a_colonna(d, t, quote=None):
    """Stringe una tabella alla larghezza della colonna (le tabelle del Word
    nascono larghe quanto la pagina e nel corpo a due colonne uscirebbero dai
    bordi). quote = proporzioni delle colonne; default parti uguali."""
    from docx.oxml import OxmlElement
    larga = _larghezza_colonna(d)
    grid0 = t._tbl.find(W + 'tblGrid')
    n_col = len(grid0.findall(W + 'gridCol')) if grid0 is not None else len(t.columns)
    quote = quote or [1.0 / n_col] * n_col
    colonne = [int(larga * q) for q in quote]
    tbl = t._tbl
    tblpr = tbl.tblPr
    for vecchio in tblpr.findall(W + 'tblW') + tblpr.findall(W + 'tblLayout')             + tblpr.findall(W + 'tblInd'):
        tblpr.remove(vecchio)
    tblw = OxmlElement('w:tblW')
    tblw.set(W + 'w', str(larga))
    tblw.set(W + 'type', 'dxa')
    tblpr.append(tblw)
    layout = OxmlElement('w:tblLayout')
    layout.set(W + 'type', 'fixed')
    tblpr.append(layout)
    grid = tbl.find(W + 'tblGrid')
    if grid is not None:
        for vecchia in list(grid):
            grid.remove(vecchia)
        for w in colonne:
            gc = OxmlElement('w:gridCol')
            gc.set(W + 'w', str(w))
            grid.append(gc)
    for tr in tbl.findall(W + 'tr'):
        pos = 0
        for tc in tr.findall(W + 'tc'):
            tcpr = tc.find(W + 'tcPr')
            if tcpr is None:
                tcpr = OxmlElement('w:tcPr')
                tc.insert(0, tcpr)
            span = tcpr.find(W + 'gridSpan')
            n = int(span.get(W + 'val')) if span is not None else 1
            for vecchio in tcpr.findall(W + 'tcW'):
                tcpr.remove(vecchio)
            tcw = OxmlElement('w:tcW')
            tcw.set(W + 'w', str(sum(colonne[pos:pos + n])))
            tcw.set(W + 'type', 'dxa')
            tcpr.insert(0, tcw)
            pos += n


def _margine_sopra(d, contract):
    """Margine superiore che contiene davvero l'intestazione (immagine
    dell'evento al 75%): senza, nelle sezioni a colonne LibreOffice la
    sovrappone al testo."""
    img = getattr(contract.event, 'email_header_image', None)
    if not img:
        return
    from PIL import Image
    from docx.shared import Mm
    with Image.open(img.path) as im:
        w, h = im.size
    for sez in d.sections:
        utile = sez.page_width - sez.left_margin - sez.right_margin
        altezza = int(utile * 0.75 * h / w)
        minimo = sez.header_distance + altezza + Mm(3)
        if sez.top_margin < minimo:
            sez.top_margin = minimo


COLORE_NOTA = 'FFF4CC'


def _bordo(tcpr, lato, nessuno):
    from docx.oxml import OxmlElement
    bordi = tcpr.find(W + 'tcBorders')
    if bordi is None:
        bordi = OxmlElement('w:tcBorders')
        tcpr.append(bordi)
    for vecchio in bordi.findall(W + lato):
        bordi.remove(vecchio)
    if nessuno:
        b = OxmlElement(f'w:{lato}')
        b.set(W + 'val', 'nil')
        bordi.append(b)


def _evidenzia_riga(tr, fondo=True, bordo_sotto=True):
    """Fondo evidenziato (e, se richiesto, niente bordo inferiore) sulle
    celle di una riga: la riga del giorno che ha una nota."""
    from docx.oxml import OxmlElement
    for tc in tr.findall(W + 'tc'):
        tcpr = tc.find(W + 'tcPr')
        if tcpr is None:
            tcpr = OxmlElement('w:tcPr')
            tc.insert(0, tcpr)
        if fondo:
            for vecchio in tcpr.findall(W + 'shd'):
                tcpr.remove(vecchio)
            shd = OxmlElement('w:shd')
            shd.set(W + 'val', 'clear')
            shd.set(W + 'color', 'auto')
            shd.set(W + 'fill', COLORE_NOTA)
            tcpr.append(shd)
        if not bordo_sotto:
            _bordo(tcpr, 'bottom', True)


def _riga_nota(t, modello, etichetta, testo):
    """Riga su tutta la larghezza sotto il giorno, con la nota in grassetto
    su fondo chiaro: le note (es. 'NON PER ALLESTIMENTO') non devono sfuggire."""
    from docx.oxml import OxmlElement
    from docx.table import _Row
    tr = copy.deepcopy(modello)
    celle = tr.findall(W + 'tc')
    for extra in celle[1:]:
        tr.remove(extra)
    tc = celle[0]
    tcpr = tc.find(W + 'tcPr')
    if tcpr is None:
        tcpr = OxmlElement('w:tcPr')
        tc.insert(0, tcpr)
    for vecchio in tcpr.findall(W + 'gridSpan') + tcpr.findall(W + 'tcW'):
        tcpr.remove(vecchio)
    span = OxmlElement('w:gridSpan')
    span.set(W + 'val', str(len(celle)))
    tcpr.append(span)
    shd = OxmlElement('w:shd')
    shd.set(W + 'val', 'clear')
    shd.set(W + 'color', 'auto')
    shd.set(W + 'fill', COLORE_NOTA)
    for vecchio in tcpr.findall(W + 'shd'):
        tcpr.remove(vecchio)
    tcpr.append(shd)
    _bordo(tcpr, 'top', True)            # attaccata alla riga del suo giorno
    t._tbl.append(tr)
    riga = _Row(tr, t)
    cella = riga.cells[0]
    for extra in cella.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    p = cella.paragraphs[0]
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    _stile_run(p.add_run(etichetta), CORPO, True)
    _stile_run(p.add_run(testo), CORPO, False)


def _frase_accesso(t, contract):
    """Subito dopo la tabella orari: l'indirizzo da cui si entra per montaggio
    e smontaggio (se indicato sull'evento) e la porta di accesso dello stand."""
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph
    from docx.shared import Pt
    en = (contract.language or 'it') == 'en'
    porta = _porta_accesso(contract)
    indirizzo = ' - '.join(r.strip() for r in (
        getattr(contract.event, 'montaggio_indirizzo', '') or '').splitlines() if r.strip())
    dettagli = [r.strip() for r in (
        getattr(contract.event, 'montaggio_dettagli', '') or '').splitlines() if r.strip()]

    pezzi = []                                  # [(etichetta in grassetto, testo)]
    if indirizzo:
        pezzi.append(('Set-up and dismantling access address: ' if en else
                      'Indirizzo di accesso per montaggio e smontaggio: ', indirizzo))
        pezzi += [('', r) for r in dettagli]
    if porta:
        pezzi.append((("For the confirmed stand you can access the hall (for set-up and "
                       f"dismantling) through entrance no. {porta}.") if en else
                      ("Per lo stand confermato potrete accedere al padiglione (per le "
                       f"fasi di montaggio e smontaggio) tramite l'accesso n° {porta}."), ''))
    dopo = t._tbl
    for i, (etichetta, testo) in enumerate(pezzi):
        el = OxmlElement('w:p')
        dopo.addnext(el)
        dopo = el
        p = Paragraph(el, t._parent)
        p.paragraph_format.space_before = Pt(8 if i == 0 else 2)
        if etichetta:
            _stile_run(p.add_run(etichetta), CORPO, True)
        if testo:
            _stile_run(p.add_run(testo), CORPO, False)


def _svuota_intestazioni(d):
    """Toglie testo e immagini di header/footer del Word: li rimette il
    sistema con i dati dell'evento, come nel contratto."""
    for sez in d.sections:
        for parte in (sez.header, sez.footer, sez.first_page_header,
                      sez.first_page_footer, sez.even_page_header,
                      sez.even_page_footer):
            try:
                if parte.is_linked_to_previous:
                    continue
                for t in list(parte.tables):
                    t._tbl.getparent().remove(t._tbl)
                ps = parte.paragraphs
                for p in ps[1:]:
                    p._p.getparent().remove(p._p)
                if ps:
                    for r in list(ps[0].runs):
                        r._r.getparent().remove(r._r)
                    for campo in ps[0]._p.findall(W + 'fldSimple'):
                        ps[0]._p.remove(campo)
            except Exception:
                continue


_ORDINE_DOPO_COLS = ('formProt', 'vAlign', 'noEndnote', 'titlePg', 'textDirection',
                     'bidi', 'rtlGutter', 'docGrid', 'printerSettings', 'sectPrChange')


def _imposta_sezione(sectpr, colonne, continua):
    """Numero di colonne e interruzione 'continua' (stessa pagina)."""
    from docx.oxml import OxmlElement
    for tag in ('cols', 'type'):
        for vecchio in sectpr.findall(W + tag):
            sectpr.remove(vecchio)
    cols = OxmlElement('w:cols')
    cols.set(W + 'num', str(colonne))
    cols.set(W + 'space', '284')                 # 0,5 cm fra le colonne
    dopo = next((c for c in sectpr if c.tag.split('}')[1] in _ORDINE_DOPO_COLS), None)
    if dopo is not None:
        dopo.addprevious(cols)
    else:
        sectpr.append(cols)
    if continua:
        tipo = OxmlElement('w:type')
        tipo.set(W + 'val', 'continuous')
        pgsz = sectpr.find(W + 'pgSz')
        if pgsz is not None:
            pgsz.addprevious(tipo)
        else:
            sectpr.insert(0, tipo)


def _inizio_parte_finale(d, dopo_el):
    """Primo elemento della parte finale a tutta larghezza: l'ULTIMO articolo
    (es. «26. Legge applicabile e foro competente»), con firme e dichiarazione
    ex 1341-1342 che lo seguono. Se il Word non ha titoli di articolo, si
    parte dal primo «Data ____»."""
    body = d.element.body
    elementi = list(body.iterchildren())
    try:
        da = elementi.index(dopo_el) + 1
    except ValueError:
        da = 0
    ultimo_titolo = None
    for el in elementi[da:]:
        if el.tag != W + 'p':
            continue
        stile = el.find(f'{W}pPr/{W}pStyle')
        if stile is not None and stile.get(W + 'val', '').lower().replace(' ', '') in (
                'heading1', 'titolo1'):
            ultimo_titolo = el
    if ultimo_titolo is not None:
        return ultimo_titolo
    import re
    for el in elementi[da:]:
        testo = ''.join(t.text or '' for t in el.iter(W + 't')).strip()
        if el.tag == W + 'p' and re.match(r'^(Data|Date)\s*_{3,}', testo):
            return el
    return None


def _due_colonne(d, fine_intestazione):
    """Tre parti: titolo e riquadro dati a tutta larghezza; il corpo degli
    articoli su due colonne (LibreOffice le pareggia in altezza alla fine);
    l'ultimo articolo, le firme e la dichiarazione ex 1341-1342 di nuovo a
    tutta larghezza. Sezioni 'continue': nessun salto di pagina, stessa
    intestazione (i riferimenti a header/footer sono copiati in ogni sezione)."""
    from docx.oxml import OxmlElement
    from docx.table import Table
    body = d.element.body
    sect_finale = body.find(W + 'sectPr')
    if sect_finale is None or fine_intestazione is None:
        return

    def _chiudi_sezione_su(p_el, colonne, continua):
        ppr = p_el.find(W + 'pPr')
        if ppr is None:
            ppr = OxmlElement('w:pPr')
            p_el.insert(0, ppr)
        sp = copy.deepcopy(sect_finale)
        _imposta_sezione(sp, colonne, continua)
        ppr.append(sp)

    finale = _inizio_parte_finale(d, fine_intestazione._p)
    # tabelle del corpo (non della parte finale): strette alla colonna
    for el in list(body.iterchildren(W + 'tbl')):
        if finale is not None and _viene_dopo(body, el, finale):
            continue
        if not _viene_dopo(body, el, fine_intestazione._p):
            continue                    # tabellina dati in testa: tutta larghezza
        tb = Table(el, d)
        intest = ' '.join(c.text.lower() for c in tb.rows[0].cells)
        if 'orario' in intest or 'time' in intest:
            continue                    # tabella orari: gia' 30/40/30
        try:
            _adatta_a_colonna(d, tb)
        except Exception:
            pass

    # sezione 1: fino al riquadro dati, una colonna
    _chiudi_sezione_su(fine_intestazione._p, 1, False)
    if finale is None:
        _imposta_sezione(sect_finale, 2, True)
        return
    # sezione 2: il corpo, due colonne, chiusa su un paragrafo vuoto dedicato
    separatore = OxmlElement('w:p')
    finale.addprevious(separatore)
    _chiudi_sezione_su(separatore, 2, True)
    # sezione finale: ultimo articolo e firme, una colonna
    _imposta_sezione(sect_finale, 1, True)


def _viene_dopo(body, el, riferimento):
    elementi = list(body.iterchildren())
    return elementi.index(el) > elementi.index(riferimento)


def _contatti_su_una_riga(d):
    """Righe «etichetta: indirizzo email» (es. «gestione amministrativa:
    amministrazione@valet.it») allineate a sinistra e, se serve, con il
    carattere ridotto quanto basta per stare su una riga della colonna."""
    import re
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt
    from contracts.services.pdf_generator import _larghezza_testo_twip
    larga = _larghezza_colonna(d) - 250          # margine di sicurezza
    for p in d.paragraphs:
        testo = p.text.strip()
        if not re.match(r'^[^:@]{3,80}:\s*\S+@\S+$', testo):
            continue
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        runs = [r for r in p.runs if r.text]
        punti = max((r.font.size.pt if r.font.size else CORPO) for r in runs)
        # il grassetto (l'etichetta) e' circa il 10% piu' largo
        serve = sum(_larghezza_testo_twip(r.text, punti) * (1.1 if r.bold else 1.0)
                    for r in runs)
        if serve > larga:
            nuovo = max(6.5, punti * larga / serve)
            for r in runs:
                r.font.size = Pt(round(nuovo * 2) / 2)


def _etichette_a_sinistra(d):
    """Righe brevi «ETICHETTA: valore» con l'etichetta maiuscola in grassetto
    (es. «TITOLO DELLA MANIFESTAZIONE: ...»): a sinistra, non giustificate,
    altrimenti gli spazi si allargano in modo innaturale."""
    import re
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for p in d.paragraphs:
        runs = [r for r in p.runs if r.text.strip()]
        if not runs or not runs[0].bold:
            continue
        if re.match(r"^[A-ZÀÈÉÌÒÙ’' ]{3,40}:", p.text.strip()) and len(p.text) < 160:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def _a_capo_a_sinistra(d):
    """Paragrafi giustificati con a capo interni (<w:br/>): a sinistra."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    def paragrafi():
        yield from d.paragraphs
        for t in d.tables:
            for cella in t._cells:
                yield from cella.paragraphs

    for par in paragrafi():
        if par._p.findall('.//' + W + 'br') and par.alignment in (
                None, WD_ALIGN_PARAGRAPH.JUSTIFY, WD_ALIGN_PARAGRAPH.DISTRIBUTE):
            stile = par.style.paragraph_format.alignment if par.style is not None else None
            if par.alignment is None and stile not in (WD_ALIGN_PARAGRAPH.JUSTIFY,
                                                       WD_ALIGN_PARAGRAPH.DISTRIBUTE):
                continue
            par.alignment = WD_ALIGN_PARAGRAPH.LEFT


def prepara_docx(percorso, contract):
    """Personalizza IN-PLACE la copia del Word dell'allegato per il contratto.
    Ogni passo e' protetto: un Word 'strano' esce comunque, al limite meno
    rifinito."""
    from docx import Document
    ctx = contesto(contract)
    _compila_segnaposto(percorso, ctx)
    d = Document(str(percorso))
    titolo = (getattr(contract.event, 'contract_annex_title', '') or '').strip()
    fine_intestazione = {}

    def _riquadro():
        fine_intestazione['p'] = _riquadro_dati(d, contract, ctx)

    for passo in (lambda: _uniforma_stile(d),
                  lambda: _titolo(d, contract, titolo),
                  _riquadro,
                  lambda: _tabella_orari(d, contract),
                  lambda: _svuota_intestazioni(d),
                  lambda: _margine_sopra(d, contract),
                  lambda: _due_colonne(d, fine_intestazione.get('p')),
                  lambda: _contatti_su_una_riga(d),
                  lambda: _etichette_a_sinistra(d),
                  lambda: _a_capo_a_sinistra(d)):
        try:
            passo()
        except Exception as e:
            logger.warning("Allegato 2 %s: passo non applicato (%s)",
                           contract.contract_number, e)
    d.save(str(percorso))
    try:
        from contracts.services.pdf_generator import _add_header_footer_to_docx
        _add_header_footer_to_docx(percorso, contract)
    except Exception as e:
        logger.warning("Allegato 2 %s: header/footer non applicati (%s)",
                       contract.contract_number, e)
