"""Estrazione/riscrittura testi dai template DOCX per la traduzione.

Uso:
  python docx_i18n.py extract <file.docx> <segments.json>
  python docx_i18n.py apply   <file.docx> <translations.json> <out.docx>
  python docx_i18n.py tags    <file.docx>          # stampa i tag jinja

Modello: per ogni parte XML (document + headers/footers), per ogni w:p,
raggruppa i w:t CONSECUTIVI che hanno la stessa formattazione (rPr) e non
sono separati da tab/br/disegni. Ogni gruppo e' un "segmento" traducibile.
L'apply rifa' la stessa passeggiata e sostituisce il testo del primo w:t
del gruppo (svuotando gli altri), cosi' formattazione, tab e layout restano
identici.
"""
import json
import re
import shutil
import sys
import zipfile

from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
BREAKERS = {f'{{{W}}}tab', f'{{{W}}}br', f'{{{W}}}drawing', f'{{{W}}}pict'}

JINJA_RE = re.compile(r'\{\{.*?\}\}|\{%.*?%\}')


def _parts(zf):
    for name in sorted(zf.namelist()):
        if re.fullmatch(r'word/(document|header\d*|footer\d*)\.xml', name):
            yield name


def _run_key(t_el):
    """Chiave di formattazione del run che contiene il w:t."""
    r = t_el.getparent()
    while r is not None and r.tag != f'{{{W}}}r':
        r = r.getparent()
    if r is None:
        return b'<none>'
    rpr = r.find(f'{{{W}}}rPr')
    return etree.tostring(rpr) if rpr is not None else b''


def _walk_groups(root):
    """Genera (p_index, g_index, [w:t elements]) per ogni segmento."""
    for p_idx, p in enumerate(root.iter(f'{{{W}}}p')):
        groups = []
        cur_key, cur = None, []
        for el in p.iter():
            if el.tag == f'{{{W}}}t':
                key = _run_key(el)
                if cur and key == cur_key:
                    cur.append(el)
                else:
                    if cur:
                        groups.append(cur)
                    cur_key, cur = key, [el]
            elif el.tag in BREAKERS:
                if cur:
                    groups.append(cur)
                cur_key, cur = None, []
        if cur:
            groups.append(cur)
        for g_idx, g in enumerate(groups):
            yield p_idx, g_idx, g


def extract(docx_path, out_json):
    zf = zipfile.ZipFile(docx_path)
    segments = {}
    for part in _parts(zf):
        root = etree.fromstring(zf.read(part))
        for p_idx, g_idx, g in _walk_groups(root):
            text = ''.join(t.text or '' for t in g)
            if text.strip():
                segments[f'{part}:{p_idx}:{g_idx}'] = text
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(segments, f, ensure_ascii=False, indent=1)
    print(f'{docx_path}: {len(segments)} segmenti -> {out_json}')


def apply(docx_path, translations_json, out_docx):
    with open(translations_json, encoding='utf-8') as f:
        translations = json.load(f)
    shutil.copyfile(docx_path, out_docx)
    zin = zipfile.ZipFile(docx_path)
    new_parts = {}
    used = set()
    for part in _parts(zin):
        root = etree.fromstring(zin.read(part))
        changed = False
        for p_idx, g_idx, g in _walk_groups(root):
            key = f'{part}:{p_idx}:{g_idx}'
            if key not in translations:
                continue
            used.add(key)
            new_text = translations[key]
            g[0].text = new_text
            g[0].set(XML_SPACE, 'preserve')
            for t in g[1:]:
                t.text = ''
            changed = True
        if changed:
            new_parts[part] = etree.tostring(
                root, xml_declaration=True, encoding='UTF-8', standalone=True)
    missing = set(translations) - used
    if missing:
        raise SystemExit(f'ERRORE: {len(missing)} chiavi non trovate nel docx: '
                         + ', '.join(sorted(missing)[:5]))
    # riscrive lo zip sostituendo le parti cambiate
    zout = zipfile.ZipFile(out_docx, 'w', zipfile.ZIP_DEFLATED)
    for item in zin.infolist():
        data = new_parts.get(item.filename, zin.read(item.filename))
        zout.writestr(item, data)
    zout.close()
    print(f'{out_docx}: applicati {len(used)} segmenti')


def tags(docx_path):
    """Multiset dei tag jinja del documento (per confronto IT/EN)."""
    zf = zipfile.ZipFile(docx_path)
    all_tags = []
    for part in _parts(zf):
        root = etree.fromstring(zf.read(part))
        for p in root.iter(f'{{{W}}}p'):
            text = ''.join(t.text or '' for t in p.iter(f'{{{W}}}t'))
            all_tags.extend(JINJA_RE.findall(text))
    for t in sorted(all_tags):
        print(t)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'extract':
        extract(sys.argv[2], sys.argv[3])
    elif cmd == 'apply':
        apply(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'tags':
        tags(sys.argv[2])
    else:
        raise SystemExit(f'comando sconosciuto: {cmd}')
