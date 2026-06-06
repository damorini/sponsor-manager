"""
Generazione di una ContractLine a partire dallo Stand/StandBlock del contratto.
Approccio "A-snella": un Service "Spazio espositivo" per evento, prezzo dallo stand.
"""
from decimal import Decimal

from catalog.models import Service


STAND_SERVICE_CODE = "SPAZIO_ESPOSITIVO"


def get_or_create_stand_service(event):
    """
    Trova (o crea la prima volta) il Service "Spazio espositivo" dell'evento,
    usato per le righe-stand. Uno per evento.
    """
    service = Service.objects.filter(
        event=event, code=STAND_SERVICE_CODE
    ).first()
    if service:
        return service

    service = Service.objects.create(
        event=event,
        code=STAND_SERVICE_CODE,
        name={"it": "Spazio espositivo", "en": "Exhibition space"},
        category="stand",
        accounting_category="stand",
        pricing_mode="fixed",
        base_price=Decimal("0.00"),
        is_active=True,
    )
    return service


def _stand_price_and_label(contract):
    """
    Ritorna (prezzo, etichetta, marcatore) per lo stand/blocco del contratto.
    prezzo puo' essere None se non impostato. marcatore identifica la riga
    in modo univoco per evitare doppioni.
    Solleva ValueError se il contratto non ha ne' stand ne' blocco.
    """
    stand = getattr(contract, "stand", None)
    block = getattr(contract, "stand_block", None)

    if stand:
        return stand.base_price, f"Spazio espositivo - {stand.code}", f"stand:{stand.code}"
    if block:
        # Prezzo a mano se impostato, altrimenti somma dei prezzi degli stand.
        return block.effective_price, f"Spazio espositivo - Blocco {block.code}", f"block:{block.code}"
    raise ValueError("Il contratto non ha ne' uno stand ne' un blocco assegnato.")


def has_stand_line(contract):
    """True se esiste gia' una riga (viva) per lo stand/blocco di questo contratto."""
    _, _, marker = _stand_price_and_label(contract)
    # il marcatore viene salvato nelle note riga per riconoscere la riga-stand
    return contract.lines.filter(notes__contains=marker).exists()


def genera_riga_da_stand(contract):
    """
    Crea una ContractLine dallo stand/blocco del contratto.

    Ritorna una tupla (esito, messaggio):
      esito in {"creata", "gia_presente", "no_stand", "no_prezzo"}.

    IDEMPOTENTE: se la riga-stand esiste gia', non ne crea un'altra.
    """
    from contracts.models import ContractLine

    # 1) stand o blocco presente?
    try:
        price, label, marker = _stand_price_and_label(contract)
    except ValueError as e:
        return ("no_stand", str(e))

    # 2) gia' presente?
    if contract.lines.filter(notes__contains=marker).exists():
        return ("gia_presente",
                f"Esiste gia' una riga per {label}. Non ho creato doppioni.")

    # 3) prezzo impostato?
    if price is None:
        return ("no_prezzo",
                f"{label}: manca il prezzo base sullo stand/blocco. "
                "Imposta il prezzo e riprova.")

    # 4) crea la riga (il save() della riga ricalcola il totale del contratto)
    service = get_or_create_stand_service(contract.event)
    line = ContractLine(
        contract=contract,
        service=service,
        service_name_snapshot=label,
        quantity=1,
        unit_price=price,
        notes=marker,  # marcatore per idempotenza
    )
    line.save()
    return ("creata", f"Riga creata: {label} - prezzo {price}. Totale aggiornato.")
