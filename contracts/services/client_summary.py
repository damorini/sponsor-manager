"""
Aggregazione dati per la SCHEDA CLIENTE (sponsor + evento).
Usata dal generatore PDF della scheda riepilogo.
"""
from decimal import Decimal


def _money(value):
    """Decimal sicuro (mai None)."""
    return value if value is not None else Decimal('0.00')


def _scadenza_stato(due_date, saldato, soglia_giorni=15):
    """
    Stato di una scadenza:
      'saldato'      se il contratto risulta gia' pagato (residuo <= 0)
      'scaduta'      se la data e' passata
      'in scadenza'  se manca <= soglia_giorni
      'futura'       altrimenti
      ''             se la data e' assente
    """
    from datetime import date as _date
    if saldato:
        return 'saldato'
    if not due_date:
        return ''
    oggi = _date.today()
    delta = (due_date - oggi).days
    if delta < 0:
        return 'scaduta'
    if delta <= soglia_giorni:
        return 'in scadenza'
    return 'futura'


def build_client_summary(sponsor, event):
    """
    Costruisce il dizionario riepilogo per uno sponsor su un evento.

    Ritorna un dict con:
      sponsor, event,
      contracts: lista di dict (uno per contratto NON annullato), ciascuno con
        contract, numero, stand, lines (lista), subtotal, vat_amount, total,
        has_deposit, deposit_percent, deposit_amount, balance_amount,
        deposit_due_date, balance_due_date
      totals: dict con subtotal, vat_amount, total (somma su tutti i contratti)
      payments: dict con incassato, residuo, lista movimenti (succeeded)
    """
    from contracts.models import Contract, ContractStatus
    from contracts.payments import PaymentStatus

    contracts_qs = (
        Contract.objects
        .filter(sponsor=sponsor, event=event)
        .exclude(status=ContractStatus.CANCELLED)
        .order_by('contract_number')
    )

    contracts_data = []
    tot_subtotal = Decimal('0.00')
    tot_vat = Decimal('0.00')
    tot_total = Decimal('0.00')
    incassato = Decimal('0.00')
    movimenti = []

    for c in contracts_qs:
        # righe servizi
        lines = []
        for ln in c.lines.all():
            lines.append({
                'name': ln.service_name_snapshot,
                'description': (getattr(ln, 'service_description_snapshot', '') or '').strip(),
                'quantity': ln.quantity,
                'unit_price': _money(ln.unit_price),
                'line_subtotal': _money(ln.line_subtotal),  # imponibile riga (no IVA)
                'line_vat': _money(ln.line_vat),             # IVA riga
                'vat_rate': _money(ln.vat_rate),
                'line_total': _money(ln.line_total),         # totale riga (IVA incl.)
            })

        # stand / blocco
        if c.stand:
            stand_label = c.stand.code
        elif c.stand_block:
            stand_label = f"Blocco {c.stand_block.code}"
        else:
            stand_label = ""

        sub = _money(c.subtotal)
        vat = _money(c.vat_amount)
        tot = _money(c.total)
        tot_subtotal += sub
        tot_vat += vat
        tot_total += tot

        # pagamenti incassati di questo contratto (succeeded)
        incassato_contratto = Decimal('0.00')
        for p in c.payments.filter(status=PaymentStatus.SUCCEEDED):
            incassato += _money(p.amount_gross)
            incassato_contratto += _money(p.amount_gross)
            movimenti.append({
                'contract_number': c.contract_number,
                'amount': _money(p.amount_gross),
                'method': p.get_payment_method_display() if hasattr(p, 'get_payment_method_display') else '',
                'date': p.completed_at,
            })

        contracts_data.append({
            'contract': c,
            'numero': c.contract_number,
            'stand': stand_label,
            'lines': lines,
            'subtotal': sub,
            'vat_amount': vat,
            'total': tot,
            'has_deposit': c.has_deposit,
            'deposit_percent': c.deposit_percent,
            'deposit_amount': c.deposit_amount,
            'balance_amount': c.balance_amount,
            'deposit_due_date': c.deposit_due_date,
            'balance_due_date': c.balance_due_date,
            'incassato_contratto': incassato_contratto,
            'residuo_contratto': (tot - incassato_contratto),
            'deposit_stato': _scadenza_stato(c.deposit_due_date,
                                             saldato=(incassato_contratto >= tot)),
            'balance_stato': _scadenza_stato(c.balance_due_date,
                                             saldato=(incassato_contratto >= tot)),
        })

    residuo = tot_total - incassato

    return {
        'sponsor': sponsor,
        'event': event,
        'contracts': contracts_data,
        'totals': {
            'subtotal': tot_subtotal,
            'vat_amount': tot_vat,
            'total': tot_total,
        },
        'payments': {
            'incassato': incassato,
            'residuo': residuo,
            'movimenti': movimenti,
        },
    }


def build_quote_summary_rows(contract):
    """
    Righe ordinate per l'Allegato 1 del preventivo (e riusabile altrove):
    STAND in cima (con la sua descrizione), poi le altre righe servizi/dotazioni.

    Ritorna lista di dict: {name, description, quantity, line_total, is_stand}.
    La descrizione dello stand viene da stand_description_override del contratto,
    altrimenti da stand/blocco.quote_description.
    """
    from decimal import Decimal

    rows = []

    # descrizione stand (override contratto -> stand/blocco)
    stand_desc = (getattr(contract, 'stand_description_override', '') or '').strip()
    if not stand_desc:
        _obj = contract.stand or contract.stand_block
        if _obj is not None and hasattr(_obj, 'translated'):
            stand_desc = (_obj.translated('quote_description', getattr(contract, 'language', None)) or '').strip()
        else:
            stand_desc = ''

    # marcatore riga-stand (vedi stand_line.py): la riga stand ha 'stand:'/'block:' nelle notes
    stand_rows = []
    other_rows = []
    for ln in contract.lines.select_related('service').all():
        is_stand = (ln.notes or '').startswith(('stand:', 'block:'))
        row = {
            'name': ln.service_name_snapshot,
            'description': (getattr(ln, 'service_description_snapshot', '') or '').strip(),
            'quantity': ln.quantity,
            'line_subtotal': ln.line_subtotal if ln.line_subtotal is not None else Decimal('0.00'),
            'line_vat': ln.line_vat if ln.line_vat is not None else Decimal('0.00'),
            'line_total': ln.line_total if ln.line_total is not None else Decimal('0.00'),
            'is_stand': is_stand,
        }
        # se e' la riga-stand e non ha descrizione propria, usa quella dello stand
        if is_stand and not row['description'] and stand_desc:
            row['description'] = stand_desc
        (stand_rows if is_stand else other_rows).append(row)

    rows = stand_rows + other_rows
    return rows
