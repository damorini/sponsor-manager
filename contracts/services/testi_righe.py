"""Ricopia nelle righe di un preventivo i testi ATTUALI dei servizi.

Le righe del contratto tengono una copia di nome e descrizione del servizio,
fatta quando la riga viene aggiunta: correggere poi il servizio non cambia i
preventivi gia' fatti. Questo li riallinea su richiesta dell'operatore.
"""


def aggiorna_testi_righe(contract):
    """Nome e descrizione di ogni riga = quelli attuali del servizio (per la
    riga dello stand/blocco: etichetta e «Descrizione per il preventivo»),
    nella lingua del contratto. Prezzi, quantita', sconti, ordine e righe
    libere restano come sono. Ritorna quante righe sono cambiate."""
    from contracts.models import ContractLine
    from contracts.services.stand_line import _stand_price_and_label

    lang = getattr(contract, 'language', None) or 'it'
    try:
        _prezzo, etichetta, marcatore, descrizione_stand, _tipo = _stand_price_and_label(contract)
    except ValueError:
        marcatore = None

    cambiate = 0
    for riga in contract.lines.select_related('service'):
        if marcatore and marcatore in (riga.notes or ''):
            nome, descrizione = etichetta, descrizione_stand
        elif riga.service_id:
            nome = riga.service.translated('name', lang)
            descrizione = riga.service.translated('description', lang)
        else:
            continue  # riga libera: il testo e' scritto a mano
        nome = (nome or riga.service_name_snapshot)[:255]
        descrizione = descrizione or ''
        if (nome, descrizione) != (riga.service_name_snapshot, riga.service_description_snapshot or ''):
            ContractLine.objects.filter(pk=riga.pk).update(
                service_name_snapshot=nome, service_description_snapshot=descrizione)
            cambiate += 1
    return cambiate
