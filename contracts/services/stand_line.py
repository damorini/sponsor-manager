"""
Generazione di una ContractLine a partire dallo Stand/StandBlock del contratto.
Approccio "A-snella": un Service "Spazio espositivo" PER TIPOLOGIA di stand,
per evento (es. SPAZIO_ESPOSITIVO_DESK, SPAZIO_ESPOSITIVO_STAND); il prezzo
viene dal singolo stand, gli inclusi (banner/desk/sedie...) si configurano sul
servizio della tipologia. La tipologia vuota usa il codice storico
SPAZIO_ESPOSITIVO (retro-compatibile).
"""
import re
from decimal import Decimal

from catalog.models import Service


STAND_SERVICE_CODE = "SPAZIO_ESPOSITIVO"


def _stand_type_suffix(stand_type):
    """Suffisso di codice per la tipologia. '' per tipologia vuota."""
    slug = re.sub(r'[^A-Za-z0-9]+', '_', (stand_type or '').strip()).strip('_').upper()
    return f"_{slug}" if slug else ""


def stand_service_code(stand_type=""):
    """Codice del servizio 'Spazio espositivo' per la tipologia data.
    Es. ''->SPAZIO_ESPOSITIVO, 'desk'->SPAZIO_ESPOSITIVO_DESK."""
    return STAND_SERVICE_CODE + _stand_type_suffix(stand_type)


def get_or_create_stand_service(event, stand_type=""):
    """
    Trova (o crea la prima volta) il Service "Spazio espositivo" dell'evento
    PER LA TIPOLOGIA indicata. Uno per (evento, tipologia).
    """
    code = stand_service_code(stand_type)
    service = Service.objects.filter(event=event, code=code).first()
    if service:
        return service

    etichetta = (stand_type or "").strip()
    nome_it = "Spazio espositivo" + (f" - {etichetta}" if etichetta else "")
    nome_en = "Exhibition space" + (f" - {etichetta}" if etichetta else "")
    service = Service.objects.create(
        event=event,
        code=code,
        name={"it": nome_it, "en": nome_en},
        category="stand",
        accounting_category="stand",
        pricing_mode="fixed",
        base_price=Decimal("0.00"),
        is_active=True,
    )
    return service


def _block_stand_type(block):
    """Tipologia di un blocco: quella dei suoi stand se UNIFORME, altrimenti ''
    (pacchetto generico)."""
    tipi = set(t for t in block.stands.values_list('stand_type', flat=True) if t)
    return tipi.pop() if len(tipi) == 1 else ""


def _stand_price_and_label(contract):
    """
    Ritorna (prezzo, etichetta, marcatore, descrizione, stand_type) per lo
    stand/blocco. prezzo puo' essere None se non impostato. marcatore identifica
    la riga in modo univoco per evitare doppioni. descrizione = "Descrizione per
    il preventivo" nella lingua del contratto. stand_type serve a scegliere il
    pacchetto (servizio) della tipologia giusta.
    Solleva ValueError se il contratto non ha ne' stand ne' blocco.
    """
    stand = getattr(contract, "stand", None)
    block = getattr(contract, "stand_block", None)
    lang = (getattr(contract, "language", "") or "it")

    def _desc(obj):
        try:
            return (obj.translated('quote_description', lang)
                    or obj.translated('quote_description', 'it') or '')
        except Exception:
            return ''

    # Etichetta nella lingua del contratto (i preventivi EN devono mostrare
    # "Exhibition space", non "Spazio espositivo").
    base_label = "Exhibition space" if lang == 'en' else "Spazio espositivo"
    block_word = "Block" if lang == 'en' else "Blocco"

    if stand:
        return (stand.base_price, f"{base_label} - {stand.code}",
                f"stand:{stand.code}", _desc(stand), stand.stand_type or "")
    if block:
        return (block.effective_price, f"{base_label} - {block_word} {block.code}",
                f"block:{block.code}", _desc(block), _block_stand_type(block))
    raise ValueError("Il contratto non ha ne' uno stand ne' un blocco assegnato.")


def has_stand_line(contract):
    """True se esiste gia' una riga (viva) per lo stand/blocco di questo contratto."""
    _, _, marker, _, _ = _stand_price_and_label(contract)
    # il marcatore viene salvato nelle note riga per riconoscere la riga-stand
    return contract.lines.filter(notes__contains=marker).exists()


def genera_riga_da_stand(contract):
    """
    Crea una ContractLine dallo stand/blocco del contratto, usando il servizio
    "Spazio espositivo" della TIPOLOGIA dello stand (cosi' eredita gli inclusi
    giusti per quel tipo di stand).

    Ritorna una tupla (esito, messaggio):
      esito in {"creata", "gia_presente", "no_stand", "no_prezzo"}.

    IDEMPOTENTE: se la riga-stand esiste gia', non ne crea un'altra.
    """
    from contracts.models import ContractLine

    # 1) stand o blocco presente?
    try:
        price, label, marker, descrizione, stand_type = _stand_price_and_label(contract)
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

    # 3-bis) override prezzo/sconto dal contratto (impostati in fase di creazione)
    price_eff = price
    if getattr(contract, 'stand_price_override', None) is not None:
        price_eff = contract.stand_price_override

    # 4) crea la riga col servizio della tipologia (il save() ricalcola i totali
    #    e l'espansione dei servizi inclusi del pacchetto)
    service = get_or_create_stand_service(contract.event, stand_type)
    line = ContractLine(
        contract=contract,
        service=service,
        service_name_snapshot=label,
        service_description_snapshot=descrizione,
        quantity=1,
        unit_price=price_eff,
        discount_percent=contract.stand_discount_percent or Decimal('0'),
        discount_amount=contract.stand_discount_amount or Decimal('0'),
        notes=marker,  # marcatore per idempotenza
    )
    line.save()
    return ("creata", f"Riga creata: {label} - prezzo {price_eff}. Totale aggiornato.")


def applica_override_stand(contract):
    """Applica gli override di prezzo/sconto del contratto alla riga STAND gia'
    esistente. Da chiamare al salvataggio del contratto: cosi' cambiando i campi
    'Prezzo stand (override)' / 'Sconto stand %' / 'Sconto stand €' la riga si
    aggiorna. Se NESSUN override e' impostato, non tocca la riga (resta il prezzo
    base, modificabile a mano). Ritorna True se ha aggiornato la riga.
    """
    from contracts.models import ContractLine  # noqa: F401
    has_override = (
        getattr(contract, 'stand_price_override', None) is not None
        or getattr(contract, 'stand_discount_percent', None) is not None
        or getattr(contract, 'stand_discount_amount', None) is not None
    )
    if not has_override:
        return False
    try:
        _p, _l, marker, _d, _t = _stand_price_and_label(contract)
    except ValueError:
        return False
    line = contract.lines.filter(notes__contains=marker).first()
    if not line:
        return False
    base_price, *_ = _stand_price_and_label(contract)
    line.unit_price = (
        contract.stand_price_override
        if contract.stand_price_override is not None
        else (base_price if base_price is not None else line.unit_price)
    )
    line.discount_percent = contract.stand_discount_percent or Decimal('0')
    line.discount_amount = contract.stand_discount_amount or Decimal('0')
    line.save()  # ContractLine.save ricalcola riga + totali contratto
    return True
