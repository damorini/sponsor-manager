"""Impaginazione dei documenti Word (contratto, Domanda, Allegato 2) prima
della conversione in PDF: un capitolo non si spezza tra due pagine.

Se un capitolo non sta nello spazio rimasto, passa intero alla pagina dopo
(«mantieni con il successivo» su tutti i suoi paragrafi). Le tabelle non si
spezzano a meta' riga e restano unite. Un capitolo piu' lungo di una pagina
inizia comunque su una pagina nuova e poi prosegue: non c'e' altro modo.

Cos'e' un capitolo:
- se il documento usa lo stile Titolo 1 (es. il regolamento tecnico), ogni
  Titolo 1 apre un capitolo;
- altrimenti lo apre un paragrafo tutto in grassetto, breve e in MAIUSCOLO
  ("1. OBBLIGAZIONI ...", "PREMESSO CHE");
- in entrambi i casi aprono un capitolo anche una tabella con il titolo in
  maiuscolo nella prima riga ("RIEPILOGO TECNICO DELLO SPAZIO") e due o piu'
  paragrafi vuoti di fila (le firme, i blocchi della Domanda).
"""
import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

STILI_TITOLO = {'titolo1', 'heading1', 'titolo', 'title', 'sottotitolo', 'subtitle'}
SOTTOTITOLO = re.compile(r'^\d+\.\d+')


def _testo(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t'))).strip()


def _stile(p):
    ppr = p.find(qn('w:pPr'))
    s = ppr.find(qn('w:pStyle')) if ppr is not None else None
    return (s.get(qn('w:val')) or '').lower() if s is not None else ''


def _tutto_grassetto(p):
    runs = [r for r in p.iter(qn('w:r')) if _testo(r)]
    if not runs:
        return False
    for r in runs:
        rpr = r.find(qn('w:rPr'))
        b = rpr.find(qn('w:b')) if rpr is not None else None
        if b is None or b.get(qn('w:val')) in ('0', 'false'):
            return False
    return True


def _maiuscolo(t):
    lettere = [c for c in t if c.isalpha()]
    return bool(lettere) and all(c.isupper() for c in lettere)


def _interruzione(el):
    return bool(el.xpath('.//w:br[@w:type="page"]') or el.xpath('.//w:pageBreakBefore')
                or el.xpath('./w:pPr/w:sectPr'))


def _capitoli(body, usa_stili):
    """Gruppi di elementi del corpo (paragrafi e tabelle), uno per capitolo."""
    capitoli, corrente, vuoti = [], [], 0

    def chiudi():
        nonlocal corrente
        if corrente:
            capitoli.append(corrente)
        corrente = []

    for el in body.iterchildren():
        tag = el.tag.split('}')[1]
        if tag == 'p':
            t = _testo(el)
            if not t:
                vuoti += 1
                if vuoti >= 2 or _interruzione(el):
                    chiudi()
                continue
            vuoti = 0
            if usa_stili:
                apre = _stile(el) in STILI_TITOLO
            else:
                # "3.3 RINUNCIA ..." e' un sottotitolo: resta nell'articolo 3
                apre = (len(t) <= 120 and _tutto_grassetto(el) and _maiuscolo(t)
                        and not SOTTOTITOLO.match(t))
            if apre or _interruzione(el):
                chiudi()
            corrente.append(el)
        elif tag == 'tbl':
            vuoti = 0
            righe = el.findall(qn('w:tr'))
            titolo = _testo(righe[0]) if righe else ''
            if len(titolo) <= 120 and _maiuscolo(titolo) and len(righe) > 1:
                chiudi()
            corrente.append(el)
        else:  # sectPr finale e simili
            chiudi()
    chiudi()
    return capitoli


def _imposta(ppr_parent, tag):
    ppr = ppr_parent.find(qn('w:pPr'))
    if ppr is None:
        ppr = OxmlElement('w:pPr')
        ppr_parent.insert(0, ppr)
    if ppr.find(qn(tag)) is None:
        ppr.append(OxmlElement(tag))


def _riga_non_spezzabile(tr):
    trpr = tr.find(qn('w:trPr'))
    if trpr is None:
        trpr = OxmlElement('w:trPr')
        tr.insert(0, trpr)
    if trpr.find(qn('w:cantSplit')) is None:
        trpr.append(OxmlElement('w:cantSplit'))


def tieni_capitoli_interi(docx_path):
    """Modifica il .docx sul posto. Ritorna il numero di capitoli trovati."""
    doc = Document(str(docx_path))
    body = doc.element.body
    usa_stili = any(_stile(p) in ('titolo1', 'heading1') for p in body.iterchildren(qn('w:p')))
    capitoli = _capitoli(body, usa_stili)
    for cap in capitoli:
        for i, el in enumerate(cap):
            ultimo = i == len(cap) - 1
            if el.tag == qn('w:tbl'):
                righe = el.findall(qn('w:tr'))
                for j, tr in enumerate(righe):
                    _riga_non_spezzabile(tr)
                    if not (ultimo and j == len(righe) - 1):
                        for p in tr.iter(qn('w:p')):
                            _imposta(p, 'w:keepNext')
            else:
                _imposta(el, 'w:keepLines')
                if not ultimo:
                    _imposta(el, 'w:keepNext')
    doc.save(str(docx_path))
    return len(capitoli)
