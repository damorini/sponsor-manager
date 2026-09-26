from django import template
from django.template.defaultfilters import linebreaksbr
from django.utils.html import conditional_escape, format_html_join
from django.utils.safestring import mark_safe

from core.elenco import voci_elenco

register = template.Library()


@register.filter(needs_autoescape=True)
def elenco_puntato(testo, autoescape=True):
    """Elenco puntato <ul> se la descrizione e' un elenco, altrimenti il testo
    con gli a capo."""
    voci = voci_elenco(testo)
    if not voci:
        return linebreaksbr(testo, autoescape=autoescape)
    return mark_safe('<ul class="elenco" style="list-style:disc; margin:2px 0 0; padding-left:14px;">' + format_html_join(
        '', '<li>{}</li>', ((conditional_escape(v),) for v in voci)) + '</ul>')
