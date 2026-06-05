from django import template
from django.utils.translation import gettext as _

register = template.Library()

_STATUS = {
    'draft': 'Bozza', 'sent': 'Inviato', 'pending_payment': 'In attesa pagamento',
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
