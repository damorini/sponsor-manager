from django import template
from django.utils.translation import gettext as _

register = template.Library()

# NB: etichette dal punto di vista del CLIENTE (il portale è la sua vista).
# 'sent' = il preventivo gli è stato inviato e attende la SUA conferma → "Da confermare".
_STATUS = {
    'draft': 'Bozza', 'sent': 'Da confermare', 'pending_payment': 'In attesa pagamento',
    'signed': 'Firmato', 'active': 'Attivo', 'completed': 'Completato', 'cancelled': 'Annullato',
}
_KIND = {'main': 'Principale', 'addon': 'Addon ecommerce', 'addendum': 'Addendum'}
_PAYMETHOD = {'paypal': 'PayPal', 'bank_transfer': 'Bonifico', 'installments': 'Rateale', 'other': 'Altro'}
_PAYSTATUS = {
    'pending': 'In attesa', 'processing': 'In elaborazione', 'succeeded': 'Completato',
    'failed': 'Fallito', 'refunded': 'Rimborsato', 'partial_refund': 'Rimborso parziale',
}

@register.filter
def status_label(value):
    return _(_STATUS.get(value, value or ''))

@register.filter
def kind_label(value):
    return _(_KIND.get(value, value or ''))

@register.filter
def paymethod_label(value):
    return _(_PAYMETHOD.get(value, value or ''))

@register.filter
def paystatus_label(value):
    return _(_PAYSTATUS.get(value, value or ''))


@register.filter
def deadline_label(value):
    """Traduce i titoli di scadenza noti (set fisso); il resto resta invariato."""
    return _(value or '')


@register.filter
def deadline_status_label(deadline):
    """Stato di una scadenza DAL PUNTO DI VISTA DEL CLIENTE (speculare all'admin).

    Il portale e' la vista del cliente: cio' che il fornitore "riceve" dal
    cliente, per il cliente e' "inviato"; le scadenze di pagamento usano i
    verbi del pagamento. Lato admin restano i termini del fornitore (Ricevuto).
    """
    status = getattr(deadline, 'status', '') or ''
    dtype = (getattr(deadline, 'deadline_type', '') or '').lower()
    is_payment = dtype.startswith('pagament')
    done = 'Pagato' if is_payment else 'Inviato'
    todo = 'Da pagare' if is_payment else 'Da inviare'
    return _({
        'pending': todo,
        'reminder_sent': todo,
        'overdue': todo + ' (in ritardo)',
        'received': done,
        'waived': 'Esonerato',
    }.get(status, todo))
