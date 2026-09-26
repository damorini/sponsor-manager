"""Caratteristiche complete dello spazio assegnato allo Sponsor (misure,
tipologia, altezza massima di allestimento, potenza elettrica, acqua,
internet, accesso, altre caratteristiche), per il Regolamento tecnico e per
la mail del PASS allestimento."""
from venues.models import misura


def _stand(contract):
    if contract.stand_id:
        return [contract.stand]
    if contract.stand_block_id:
        return list(contract.stand_block.stands.all().order_by('code'))
    return []


def _si_no(valore, en):
    return ('yes' if valore else 'no') if en else ('sì' if valore else 'no')


def voci_stand(s, en=False):
    """[(etichetta, valore)] di uno stand; solo i dati compilati."""
    voci = []
    if s.stand_type:
        voci.append(('Type' if en else 'Tipologia', s.stand_type))
    if s.dimensioni_testo:
        voci.append(('Size' if en else 'Misure', s.dimensioni_testo))
    if s.max_height_meters:
        voci.append(('Maximum set-up height' if en else 'Altezza max di allestimento',
                     f"{misura(s.max_height_meters)} m"))
    if s.has_power or s.power_kw:
        voci.append(('Electrical connection' if en else 'Allaccio elettrico',
                     f"{misura(s.power_kw)} kW" if s.power_kw else _si_no(True, en)))
    else:
        voci.append(('Electrical connection' if en else 'Allaccio elettrico', _si_no(False, en)))
    voci.append(('Water connection' if en else 'Allaccio idrico', _si_no(s.has_water, en)))
    voci.append(('Internet', _si_no(s.has_internet, en)))
    if (s.access_door or '').strip():
        voci.append(('Hall access no.' if en else 'Accesso al padiglione n°',
                     s.access_door.strip()))
    altro = (s.caratteristiche or '').strip()
    if altro:
        voci.append(('Other features' if en else 'Altre caratteristiche', altro))
    return voci


def schede(contract):
    """Una scheda per stand: [{'codice', 'voci'}] (piu' d'una per un blocco)."""
    en = (contract.language or 'it') == 'en'
    return [{'codice': s.code, 'voci': voci_stand(s, en)} for s in _stand(contract)]
