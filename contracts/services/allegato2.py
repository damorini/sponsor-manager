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
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _etichetta_stand(contract):
    stand = getattr(contract, 'stand', None)
    if stand:
        return stand.code
    blocco = getattr(contract, 'stand_block', None)
    return blocco.code if blocco else '-'


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
    }


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
        if stile == 'Title':
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                _stile_run(r, 14, True)
        elif stile == 'Subtitle':
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                _stile_run(r, 11, True)
                r.font.italic = False
        elif stile.startswith('Heading'):
            for r in p.runs:
                _stile_run(r, 9, True)
        else:
            if p.alignment is None or p.alignment == WD_ALIGN_PARAGRAPH.LEFT:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            for r in p.runs:
                _stile_run(r, 9)

    for p in d.paragraphs:
        _paragrafo(p)
    for t in d.tables:
        for n, riga in enumerate(t.rows):
            for cella in riga.cells:
                for p in cella.paragraphs:
                    for r in p.runs:
                        # prima riga = intestazione: in grassetto
                        _stile_run(r, 9, True if n == 0 and len(t.rows) > 1 else None)


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
    righe = [('Exhibiting company' if en else 'Azienda espositrice', ctx['azienda']),
             ('Stand no.' if en else 'Stand n.', ctx['stand']),
             ('Contract no.' if en else 'Contratto n.', ctx['contratto'])]
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
    for etichetta, valore in righe:
        p = _nuovo_dopo(ultimo)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        _stile_run(p.add_run(f"{etichetta}: "), 10, True)
        _stile_run(p.add_run(str(valore or '-')), 10, False)
        ultimo = p
    _nuovo_dopo(ultimo)                         # riga vuota di stacco


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
                if g.notes:
                    testi[2] += f" ({g.notes})"
            for cella, testo in zip(riga.cells, testi):
                ps = cella.paragraphs
                for extra in ps[1:]:
                    extra._p.getparent().remove(extra._p)
                p = ps[0]
                for r in list(p.runs):
                    r._r.getparent().remove(r._r)
                _stile_run(p.add_run(testo), 9)
        return True
    return False


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


def prepara_docx(percorso, contract):
    """Personalizza IN-PLACE la copia del Word dell'allegato per il contratto.
    Ogni passo e' protetto: un Word 'strano' esce comunque, al limite meno
    rifinito."""
    from docx import Document
    ctx = contesto(contract)
    _compila_segnaposto(percorso, ctx)
    d = Document(str(percorso))
    titolo = (getattr(contract.event, 'contract_annex_title', '') or '').strip()
    for passo in (lambda: _uniforma_stile(d),
                  lambda: _titolo(d, contract, titolo),
                  lambda: _riquadro_dati(d, contract, ctx),
                  lambda: _tabella_orari(d, contract),
                  lambda: _svuota_intestazioni(d)):
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
