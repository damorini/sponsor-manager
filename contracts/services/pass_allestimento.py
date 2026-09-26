"""PASS ALLESTIMENTO: email allo Sponsor che ha completato le procedure
amministrative. Riporta stand, accesso al padiglione, giorni e orari di
allestimento/disallestimento e le indicazioni per spedire i materiali al
magazzino. In copia all'amministrazione; la data d'invio resta sul contratto
(colonna «PASS allestimento» nella lista dei contratti)."""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

TEMPLATE = 'pass_allestimento'
CC_AMMINISTRAZIONE = ['amministrazione@valet.it']
OGGETTO = {
    'it': "PASS ALLESTIMENTO · {evento}",
    'en': "SET-UP PASS · {evento}",
}
GIORNI_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _lingua(contract):
    return 'en' if (contract.language or 'it') == 'en' else 'it'


def _righe(testo):
    return [r.strip() for r in (testo or '').splitlines() if r.strip()]


def giorni(contract, lingua='it'):
    """Giorni di allestimento/disallestimento dell'evento, in ordine."""
    righe = []
    for g in contract.event.setup_days.all().order_by('date', 'start_time'):
        allest = g.kind == 'allestimento'
        righe.append({
            'tipo': ('Allestimento' if allest else 'Disallestimento') if lingua == 'it'
                    else ('Set-up' if allest else 'Dismantling'),
            'giorno': g.giorno_settimana if lingua == 'it' else GIORNI_EN[g.date.weekday()],
            'data': g.date,
            'dalle': g.start_time,
            'alle': g.end_time,
            'note': (g.notes or '').strip(),
            'allestimento': allest,
        })
    return righe


def contesto(contract):
    from contracts.services.allegato2 import (
        _date_evento, _etichetta_stand, _porta_accesso,
    )
    from contracts.services.pdf_generator import _event_for_template
    ev = contract.event
    lingua = _lingua(contract)
    return {
        'contract': contract,
        'sponsor': contract.sponsor,
        'event': ev,
        'event_name': nome_evento(contract),
        'contact': destinatario(contract),
        'stand': _etichetta_stand(contract),
        **_stand_o_blocco(contract, lingua),
        'accesso': _porta_accesso(contract),
        'date_evento': _date_evento(ev),
        'sede': _event_for_template(ev).location,
        'giorni': giorni(contract, lingua),
        'spazio': _spazio(contract),
        'montaggio_indirizzo': _righe(getattr(ev, 'montaggio_indirizzo', '')),
        'montaggio_dettagli': _righe(getattr(ev, 'montaggio_dettagli', '')),
        'regole_montaggio': _righe(getattr(ev, 'regole_montaggio', '')),
        'magazzino_ritiro': _righe(getattr(ev, 'magazzino_ritiro', '')),
        'magazzino_indirizzo': _righe(getattr(ev, 'magazzino_indirizzo', '')),
        'magazzino_dettagli': _righe(getattr(ev, 'magazzino_dettagli', '')),
    }


def _stand_o_blocco(contract, lingua):
    """Etichetta e testo dello spazio: «Stand n. 1-A» oppure, per un blocco,
    «Blocco SELTEC» con «stand n° 29-A e 30-A»."""
    en = lingua == 'en'
    blocco = contract.stand_block if contract.stand_block_id and not contract.stand_id else None
    if blocco is None:
        return {'blocco': '', 'stand_del_blocco': ''}
    codici = list(blocco.stands.order_by('code').values_list('code', flat=True))
    if len(codici) > 1:
        elenco = ", ".join(codici[:-1]) + (" and " if en else " e ") + codici[-1]
    else:
        elenco = codici[0] if codici else ''
    return {'blocco': blocco.code, 'stand_del_blocco': elenco}


def _spazio(contract):
    from contracts.services.caratteristiche_spazio import schede
    return schede(contract, con_accesso=False)


def destinatario(contract):
    """Contatto operativo (come per l'invio del contratto), poi il principale."""
    from contracts.services.pdf_generator import _get_operational_contact
    c = _get_operational_contact(contract)
    if c is not None and getattr(c, 'email', ''):
        return c
    sp = contract.sponsor
    c = getattr(sp, 'primary_contact', None)
    if c is not None and getattr(c, 'email', ''):
        return c
    return sp.contacts.exclude(email='').first()


def nome_evento(contract):
    ev = contract.event
    if hasattr(ev, 'get_name'):
        return ev.get_name(_lingua(contract)) or ''
    return str(ev.name)


def oggetto(contract):
    return OGGETTO[_lingua(contract)].format(evento=nome_evento(contract))


def anteprima(contract):
    """(oggetto, html) della email, SENZA inviarla."""
    from contracts.services.email_sender import _render_email_body, build_common_context
    lingua = _lingua(contract)
    ctx = build_common_context(contesto(contract), lingua)
    sogg = oggetto(contract)
    ctx['subject'] = sogg
    html, sogg_admin = _render_email_body(
        TEMPLATE, lingua, ctx, event_type=getattr(contract.event, 'event_type', None))
    sogg = sogg_admin or sogg
    azienda = contract.sponsor.legal_name
    if azienda and not sogg.startswith(azienda):
        sogg = f"{azienda} – {sogg}"
    return sogg, html


def pdf(contract):
    """Il PASS in PDF (stesso contenuto della mail), da allegare. Ritorna
    (nome_file, bytes) oppure None se la conversione non riesce."""
    try:
        import re
        from weasyprint import HTML
        _oggetto, html = anteprima(contract)
        html = html.replace('&#127881;', '').replace('\U0001F389', '')
        # carattere piu' piccolo della mail (circa -20%)
        html = re.sub(r'font-size:\s*(\d+(?:\.\d+)?)px',
                      lambda m: f"font-size:{float(m.group(1)) * 0.8:.1f}px", html)
        # a fine pagina si va a capo solo fra blocchi interi: paragrafi, righe
        # di tabella, riquadri e titoli non si spezzano
        stile = ('<style>@page { size: A4; margin: 12mm 10mm; } '
                 'body { background: #ffffff !important; } '
                 'p, li, tr, h1, h2, h3 { break-inside: avoid; page-break-inside: avoid; } '
                 'table table { break-inside: avoid; page-break-inside: avoid; } '
                 'h1, h2, h3 { break-after: avoid; page-break-after: avoid; } '
                 'p { orphans: 4; widows: 4; }</style>')
        html = re.sub(r'(</head>)', stile + r'\1', html, count=1) \
            if '</head>' in html else stile + html
        from django.conf import settings
        base = getattr(settings, 'SITE_URL', '') or None
        dati = HTML(string=html, base_url=base).write_pdf()
        numero = (contract.contract_number or str(contract.pk)).replace('/', '-')
        return (f"PASS_allestimento_{numero}.pdf", dati)
    except Exception as e:
        logger.warning("PASS allestimento %s: PDF non generato (%s)",
                       contract.contract_number, e)
        return None


def invia(contract, utente=None):
    """Invia il PASS e segna data e ora sul contratto. Solleva ValueError se
    manca l'indirizzo email dello Sponsor."""
    from contracts.services.email_sender import send_email
    c = destinatario(contract)
    if c is None:
        raise ValueError("nessun contatto con indirizzo email per lo Sponsor")
    allegato = pdf(contract)
    send_email(
        template_name=TEMPLATE,
        attachments=[(allegato[0], allegato[1], 'application/pdf')] if allegato else None,
        context=contesto(contract),
        to=[c.email],
        cc=list(CC_AMMINISTRAZIONE),
        subject=oggetto(contract),
        language=_lingua(contract),
        related_to=contract,
        communication_type='pass_allestimento',
        triggered_by_user=utente,
    )
    contract.pass_allestimento_inviato_il = timezone.now()
    contract.save(update_fields=['pass_allestimento_inviato_il', 'updated_at'])
    logger.info("PASS allestimento %s inviato a %s (CC amministrazione)",
                contract.contract_number, c.email)
    return c.email
