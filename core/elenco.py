"""Descrizioni dei servizi scritte come elenco («· Area nuda· Appendimento ...»
oppure una voce per riga col trattino): le voci separate, per stamparle come
elenco puntato in preventivo, Domanda di ammissione e portale."""
import re

_SEPARATORE = re.compile(r'\s*[·•]\s*')
_INIZIO = re.compile(r'^\s*[-–·•*]\s+')


def voci_elenco(testo):
    """Lista delle voci se il testo e' un elenco, altrimenti None.

    E' un elenco se contiene «·»/«•» come separatori, oppure se tutte le
    righe (almeno due) iniziano con un trattino o un pallino."""
    testo = (testo or '').strip()
    if not testo:
        return None
    righe = [r for r in testo.splitlines() if r.strip()]
    if '·' in testo or '•' in testo:
        voci = [v.strip() for r in righe for v in _SEPARATORE.split(r) if v.strip()]
        voci = [_INIZIO.sub('', v).strip() for v in voci]
        return voci if len(voci) >= 2 else None
    if len(righe) >= 2 and all(_INIZIO.match(r) for r in righe):
        return [_INIZIO.sub('', r).strip() for r in righe]
    return None
