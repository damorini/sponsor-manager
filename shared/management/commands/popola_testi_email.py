# -*- coding: utf-8 -*-
"""Popola i 24 Template email (12 punti x ECM/NON_ECM) con testi predefiniti
curati (oggetto + corpo HTML, IT/EN) e segnaposti. Idempotente: riempie solo le
righe col corpo VUOTO (usa --force per sovrascrivere). Lascia is_active invariato
(restano NON attivi finche' non li attivi tu dall'admin)."""
from django.core.management.base import BaseCommand


def box(inner, bg="#f9fafb", border="#e5e7eb"):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border:1px solid {border}; border-radius:10px; background:{bg}; '
            f'margin:18px 0;"><tr><td style="padding:16px 20px;">{inner}</td></tr></table>')


def btn(href, label):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:26px 0;"><tr><td align="center">'
            f'<a class="button" href="{href}">{label}</a></td></tr></table>')


SIGN_IT = '<p style="margin:22px 0 0;">Cordiali saluti,<br><strong>{{ org_name|default:organizer_name }}</strong></p>'
SIGN_EN = '<p style="margin:22px 0 0;">Kind regards,<br><strong>{{ org_name|default:organizer_name }}</strong></p>'

H = lambda t, c="#1d6534": f'<h2 style="margin:0 0 12px; font-size:22px; color:{c};">{t}</h2>'

TEXTS = {
    # 1 -----------------------------------------------------------------
    'portal_invitation': {
        'subject': {'it': 'Benvenuto nel portale sponsor · {{ org_name|default:organizer_name }}',
                    'en': 'Welcome to the sponsor portal · {{ org_name|default:organizer_name }}'},
        'body': {
            'it': H('Benvenuto nel portale sponsor 👋') +
                  '<p>Gentile {{ contact.full_name }},<br>sei stato abilitato all\'accesso al portale di <strong>{{ org_name|default:organizer_name }}</strong>. Da qui gestisci in autonomia preventivi, spazi, servizi, materiali e scadenze.</p>' +
                  box('<p style="margin:0 0 8px; font-weight:600;">Le tue credenziali di accesso</p>'
                      '<p style="margin:0;">Email (nome utente): <strong>{{ user.email }}</strong><br>'
                      'Password temporanea: <strong style="font-family:monospace;">{{ temp_password }}</strong></p>') +
                  btn('{{ site_url }}{% url \'portal:login\' %}', 'Accedi al portale') +
                  '<div class="alert-warning"><strong>Consiglio:</strong> cambia la password al primo accesso, dalla pagina «I miei dati».</div>' +
                  SIGN_IT,
            'en': H('Welcome to the sponsor portal 👋') +
                  '<p>Dear {{ contact.full_name }},<br>you now have access to the portal of <strong>{{ org_name|default:organizer_name }}</strong>: manage proposals, spaces, services, materials and deadlines.</p>' +
                  box('<p style="margin:0 0 8px; font-weight:600;">Your login credentials</p>'
                      '<p style="margin:0;">Email (username): <strong>{{ user.email }}</strong><br>'
                      'Temporary password: <strong style="font-family:monospace;">{{ temp_password }}</strong></p>') +
                  btn('{{ site_url }}{% url \'portal:login\' %}', 'Go to the portal') +
                  '<div class="alert-warning"><strong>Tip:</strong> change your password on first login, from the «My data» page.</div>' +
                  SIGN_EN,
        },
    },
    # 2 -----------------------------------------------------------------
    'quote_email': {
        'subject': {'it': 'La tua proposta per {{ event_name }} · {{ contract.contract_number }}',
                    'en': 'Your proposal for {{ event_name }} · {{ contract.contract_number }}'},
        'body': {
            'it': H('La tua proposta di sponsorizzazione') +
                  '<p>Gentile {{ sponsor.legal_name }},<br>grazie per l\'interesse verso <strong>{{ event_name }}</strong>. Abbiamo preparato per voi una proposta dedicata.</p>' +
                  '<p>Trovate <strong>tutti i dettagli</strong> — spazi, servizi e importi — nel <strong>PDF allegato</strong>.</p>' +
                  '{% if contract.option_until %}<div class="alert-warning"><strong>Spazi riservati per voi fino al {{ contract.option_until|date:"d/m/Y" }}.</strong><br>Trascorsa questa data gli spazi tornano disponibili per altri sponsor.</div>{% endif %}' +
                  btn('{{ site_url }}{% url \'portal:contract_detail\' contract.id %}', 'Vedi e conferma il preventivo') +
                  SIGN_IT,
            'en': H('Your sponsorship proposal') +
                  '<p>Dear {{ sponsor.legal_name }},<br>thank you for your interest in <strong>{{ event_name }}</strong>. We have prepared a dedicated proposal for you.</p>' +
                  '<p>You will find <strong>all the details</strong> — spaces, services and amounts — in the <strong>attached PDF</strong>.</p>' +
                  '{% if contract.option_until %}<div class="alert-warning"><strong>Spaces reserved for you until {{ contract.option_until|date:"d/m/Y" }}.</strong><br>After this date the spaces become available again.</div>{% endif %}' +
                  btn('{{ site_url }}{% url \'portal:contract_detail\' contract.id %}', 'View and confirm the proposal') +
                  SIGN_EN,
        },
    },
    # 3 -----------------------------------------------------------------
    'contract_signed': {
        'subject': {'it': 'Domanda di ammissione confermata · {{ event_name }}',
                    'en': 'Admission request confirmed · {{ event_name }}'},
        'body': {
            'it': H('Domanda di ammissione confermata ✓') +
                  '<p>Gentile {{ sponsor.legal_name }},<br>la vostra partecipazione a <strong>{{ event_name }}</strong> è confermata. In allegato trovate la <strong>domanda di ammissione</strong> (contratto {{ contract.contract_number }}).</p>' +
                  '<div class="alert-success">Da questo momento la vostra presenza è riservata. Nel portale trovate scadenze, materiali da caricare e i pagamenti.</div>' +
                  btn('{{ site_url }}{% url \'portal:contracts_list\' %}', 'Vai all\'area riservata') +
                  SIGN_IT,
            'en': H('Admission request confirmed ✓') +
                  '<p>Dear {{ sponsor.legal_name }},<br>your participation in <strong>{{ event_name }}</strong> is confirmed. Attached you will find the <strong>admission request</strong> (contract {{ contract.contract_number }}).</p>' +
                  '<div class="alert-success">Your presence is now reserved. In the portal you can find deadlines, materials to upload and payments.</div>' +
                  btn('{{ site_url }}{% url \'portal:contracts_list\' %}', 'Go to your area') +
                  SIGN_EN,
        },
    },
    # 4 -----------------------------------------------------------------
    'sponsor_contract_email': {
        'subject': {'it': 'Contratto di sponsorizzazione {{ contract.contract_number }} · {{ event_name }}',
                    'en': 'Sponsorship agreement {{ contract.contract_number }} · {{ event_name }}'},
        'body': {
            'it': H('Contratto di sponsorizzazione') +
                  '<p>Gentile {{ sponsor.legal_name }},<br>a seguito della conferma del preventivo, in allegato trovate il <strong>contratto di sponsorizzazione</strong> per <strong>{{ event_name }}</strong>, completo della <strong>domanda di ammissione (Allegato 1)</strong>.</p>' +
                  '<p>Vi chiediamo di verificare i dati, firmare il contratto e restituircelo. Restiamo a disposizione per qualsiasi necessità.</p>' +
                  SIGN_IT,
            'en': H('Sponsorship agreement') +
                  '<p>Dear {{ sponsor.legal_name }},<br>following your confirmation, attached you will find the <strong>sponsorship agreement</strong> for <strong>{{ event_name }}</strong>, including the <strong>admission request (Annex 1)</strong>.</p>' +
                  '<p>Please review the details, sign and return it. We remain at your disposal.</p>' +
                  SIGN_EN,
        },
    },
    # 5 -----------------------------------------------------------------
    'payment_confirmation': {
        'subject': {'it': 'Pagamento ricevuto · {{ contract.contract_number }}',
                    'en': 'Payment received · {{ contract.contract_number }}'},
        'body': {
            'it': H('Pagamento ricevuto ✓', '#10b981') +
                  '<p>Buongiorno {{ contact.full_name }},<br>confermiamo la ricezione del pagamento per il contratto <strong>{{ contract.contract_number }}</strong> ({{ event_name }}).</p>' +
                  box('<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                      '<tr><td style="padding:4px 0;"><strong>Importo</strong></td><td align="right">€ {{ payment.amount_gross|floatformat:2 }}</td></tr>'
                      '<tr><td style="padding:4px 0;"><strong>Modalità</strong></td><td align="right">{{ payment.get_payment_method_display }}</td></tr>'
                      '<tr><td style="padding:4px 0;"><strong>Data</strong></td><td align="right">{{ payment.completed_at|date:"d/m/Y H:i" }}</td></tr>'
                      '</table>', bg="#d1fae5", border="#a7f3d0") +
                  btn('{{ portal_url }}', 'Accedi al portale') +
                  SIGN_IT,
            'en': H('Payment received ✓', '#10b981') +
                  '<p>Hello {{ contact.full_name }},<br>we confirm receipt of the payment for contract <strong>{{ contract.contract_number }}</strong> ({{ event_name }}).</p>' +
                  box('<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
                      '<tr><td style="padding:4px 0;"><strong>Amount</strong></td><td align="right">€ {{ payment.amount_gross|floatformat:2 }}</td></tr>'
                      '<tr><td style="padding:4px 0;"><strong>Method</strong></td><td align="right">{{ payment.get_payment_method_display }}</td></tr>'
                      '<tr><td style="padding:4px 0;"><strong>Date</strong></td><td align="right">{{ payment.completed_at|date:"d/m/Y H:i" }}</td></tr>'
                      '</table>', bg="#d1fae5", border="#a7f3d0") +
                  btn('{{ portal_url }}', 'Go to the portal') +
                  SIGN_EN,
        },
    },
    # 6 -----------------------------------------------------------------
    'deadline_reminder': {
        'subject': {'it': 'Promemoria: {{ deadline.title }} · scade il {{ deadline.due_date|date:"d/m/Y" }}',
                    'en': 'Reminder: {{ deadline.title }} · due on {{ deadline.due_date|date:"d/m/Y" }}'},
        'body': {
            'it': H('Promemoria scadenza') +
                  '<p>Buongiorno {{ contact.full_name }},<br>vi ricordiamo la scadenza <strong>"{{ deadline.title }}"</strong> del contratto <strong>{{ contract.contract_number }}</strong> ({{ event_name }}).</p>' +
                  box('<p style="margin:0; font-size:15px;">Prevista per il <strong style="color:#1d6534;">{{ deadline.due_date|date:"d/m/Y" }}</strong> — tra <strong>{{ days_remaining }} giorni</strong>.</p>') +
                  '{% if is_pagamento and importo_scadenza %}<div class="alert-warning"><strong>Importo da versare:</strong> € {{ importo_scadenza|floatformat:2 }} (IVA inclusa)</div>{% endif %}' +
                  '{% if deadline.description %}<p><strong>Cosa è richiesto:</strong><br>{{ deadline.description|linebreaksbr }}</p>{% endif %}' +
                  btn('{{ portal_url }}', 'Vai alla scadenza') +
                  SIGN_IT,
            'en': H('Deadline reminder') +
                  '<p>Hello {{ contact.full_name }},<br>a reminder about the deadline <strong>"{{ deadline.title }}"</strong> of contract <strong>{{ contract.contract_number }}</strong> ({{ event_name }}).</p>' +
                  box('<p style="margin:0; font-size:15px;">Due on <strong style="color:#1d6534;">{{ deadline.due_date|date:"d/m/Y" }}</strong> — in <strong>{{ days_remaining }} days</strong>.</p>') +
                  '{% if is_pagamento and importo_scadenza %}<div class="alert-warning"><strong>Amount due:</strong> € {{ importo_scadenza|floatformat:2 }} (VAT incl.)</div>{% endif %}' +
                  '{% if deadline.description %}<p><strong>What is required:</strong><br>{{ deadline.description|linebreaksbr }}</p>{% endif %}' +
                  btn('{{ portal_url }}', 'Go to the deadline') +
                  SIGN_EN,
        },
    },
    # 7 -----------------------------------------------------------------
    'deadline_overdue': {
        'subject': {'it': 'Sollecito: {{ deadline.title }} scaduta · {{ contract.contract_number }}',
                    'en': 'Reminder: {{ deadline.title }} overdue · {{ contract.contract_number }}'},
        'body': {
            'it': H('Sollecito · scadenza superata', '#dc2626') +
                  '<p>Buongiorno {{ contact.full_name }},</p>' +
                  '<div class="alert-error"><strong>Attenzione:</strong> la scadenza "<strong>{{ deadline.title }}</strong>" del contratto <strong>{{ contract.contract_number }}</strong> era prevista per il <strong>{{ deadline.due_date|date:"d/m/Y" }}</strong> ed è scaduta da {{ days_overdue }} giorni.</div>' +
                  '{% if is_pagamento and importo_scadenza %}<div class="alert-warning"><strong>Importo da versare:</strong> € {{ importo_scadenza|floatformat:2 }} (IVA inclusa)</div>{% endif %}' +
                  '<p>Vi preghiamo di provvedere al più presto dall\'area riservata. Per difficoltà a rispettare la scadenza, contattateci.</p>' +
                  btn('{{ portal_url }}', 'Regolarizza ora') +
                  '<p style="color:#6b7280; font-size:13px;">Se nel frattempo avete già provveduto, vi ringraziamo: potete considerare questa comunicazione come non inviata.</p>' +
                  SIGN_IT,
            'en': H('Reminder · deadline passed', '#dc2626') +
                  '<p>Hello {{ contact.full_name }},</p>' +
                  '<div class="alert-error"><strong>Please note:</strong> the deadline "<strong>{{ deadline.title }}</strong>" of contract <strong>{{ contract.contract_number }}</strong> was due on <strong>{{ deadline.due_date|date:"d/m/Y" }}</strong> and is {{ days_overdue }} days overdue.</div>' +
                  '{% if is_pagamento and importo_scadenza %}<div class="alert-warning"><strong>Amount due:</strong> € {{ importo_scadenza|floatformat:2 }} (VAT incl.)</div>{% endif %}' +
                  '<p>Please take care of it as soon as possible from your area. If you have any difficulty, contact us.</p>' +
                  btn('{{ portal_url }}', 'Resolve now') +
                  '<p style="color:#6b7280; font-size:13px;">If you have already taken care of this, thank you — please disregard this message.</p>' +
                  SIGN_EN,
        },
    },
    # 8 -----------------------------------------------------------------
    'option_reminder': {
        'subject': {'it': 'La tua opzione spazio scade a breve · {{ event_name }}',
                    'en': 'Your space option expires soon · {{ event_name }}'},
        'body': {
            'it': H('Promemoria opzione spazio') +
                  '<p>Buongiorno {{ contact.full_name }},<br>vi ricordiamo che l\'<strong>opzione</strong> sullo spazio espositivo del contratto <strong>{{ contract.contract_number }}</strong> ({{ event_name }}) scade il <strong style="color:#1d6534;">{{ deadline.due_date|date:"d/m/Y" }}</strong> (tra {{ days_remaining }} giorni).</p>' +
                  '<div class="alert-warning">Trascorsa tale data lo spazio tornerà disponibile e potrà essere proposto ad altri espositori. Vi invitiamo a confermarci la vostra decisione entro la scadenza.</div>' +
                  btn('{{ site_url }}{% url \'portal:contracts_list\' %}', 'Conferma la partecipazione') +
                  SIGN_IT,
            'en': H('Space option reminder') +
                  '<p>Hello {{ contact.full_name }},<br>a reminder that the <strong>option</strong> on the exhibition space of contract <strong>{{ contract.contract_number }}</strong> ({{ event_name }}) expires on <strong style="color:#1d6534;">{{ deadline.due_date|date:"d/m/Y" }}</strong> (in {{ days_remaining }} days).</p>' +
                  '<div class="alert-warning">After this date the space will become available to other exhibitors. Please confirm your decision by the deadline.</div>' +
                  btn('{{ site_url }}{% url \'portal:contracts_list\' %}', 'Confirm participation') +
                  SIGN_EN,
        },
    },
    # 9 -----------------------------------------------------------------
    'cart_recovery': {
        'subject': {'it': 'Hai lasciato dei servizi nel carrello · {{ event_name }}',
                    'en': 'You left services in your cart · {{ event_name }}'},
        'body': {
            'it': H('Hai lasciato qualcosa nel carrello 🛒') +
                  '<p>Buongiorno {{ contact.full_name }},<br>hai un carrello in sospeso per <strong>{{ event_name }}</strong>.</p>' +
                  '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0; border:1px solid #e5e7eb; border-radius:8px;">'
                  '<tr style="background:#f9fafb;"><th align="left" style="padding:10px 12px;">Servizio</th><th align="right" style="padding:10px 12px;">Q.tà</th><th align="right" style="padding:10px 12px;">Totale</th></tr>'
                  '{% for line in cart_lines %}<tr><td style="padding:10px 12px; border-top:1px solid #f3f4f6;">{{ line.service_name_snapshot }}</td><td align="right" style="padding:10px 12px; border-top:1px solid #f3f4f6;">{{ line.quantity }}</td><td align="right" style="padding:10px 12px; border-top:1px solid #f3f4f6;">€ {{ line.line_total|floatformat:2 }}</td></tr>{% endfor %}'
                  '<tr style="background:#f9fafb;"><td colspan="2" align="right" style="padding:10px 12px; font-weight:700;">Totale</td><td align="right" style="padding:10px 12px; font-weight:700;">€ {{ cart_total|floatformat:2 }}</td></tr>'
                  '</table>' +
                  '<div class="alert-warning"><strong>Nota:</strong> alcuni servizi potrebbero non essere più acquistabili a ridosso dell\'evento: ti consigliamo di completare l\'ordine per tempo.</div>' +
                  btn('{{ checkout_url }}', 'Completa l\'acquisto') +
                  SIGN_IT,
            'en': H('You left something in your cart 🛒') +
                  '<p>Hello {{ contact.full_name }},<br>you have a pending cart for <strong>{{ event_name }}</strong>.</p>' +
                  '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0; border:1px solid #e5e7eb; border-radius:8px;">'
                  '<tr style="background:#f9fafb;"><th align="left" style="padding:10px 12px;">Service</th><th align="right" style="padding:10px 12px;">Qty</th><th align="right" style="padding:10px 12px;">Total</th></tr>'
                  '{% for line in cart_lines %}<tr><td style="padding:10px 12px; border-top:1px solid #f3f4f6;">{{ line.service_name_snapshot }}</td><td align="right" style="padding:10px 12px; border-top:1px solid #f3f4f6;">{{ line.quantity }}</td><td align="right" style="padding:10px 12px; border-top:1px solid #f3f4f6;">€ {{ line.line_total|floatformat:2 }}</td></tr>{% endfor %}'
                  '<tr style="background:#f9fafb;"><td colspan="2" align="right" style="padding:10px 12px; font-weight:700;">Total</td><td align="right" style="padding:10px 12px; font-weight:700;">€ {{ cart_total|floatformat:2 }}</td></tr>'
                  '</table>' +
                  '<div class="alert-warning"><strong>Note:</strong> some services may no longer be available close to the event: we recommend completing your order in good time.</div>' +
                  btn('{{ checkout_url }}', 'Complete the purchase') +
                  SIGN_EN,
        },
    },
    # 10 ----------------------------------------------------------------
    'operator_alert': {
        'subject': {'it': '⚠ Alert Sponsor Manager',
                    'en': '⚠ Sponsor Manager alert'},
        'body': {
            'it': H('⚠ Alert Sponsor Manager', '#dc2626') +
                  '<p>Buongiorno {{ user.first_name|default:user.email }},<br>il sistema ha rilevato situazioni che richiedono attenzione:</p>' +
                  '{% if overdue_deadlines %}<h3 style="color:#dc2626; margin-top:22px;">Scadenze in ritardo ({{ overdue_deadlines|length }})</h3><ul style="padding-left:20px;">{% for d in overdue_deadlines %}<li><strong>{{ d.contract.sponsor.legal_name }}</strong> · {{ d.title }} · in ritardo di <strong>{{ d.days_overdue }} giorni</strong></li>{% endfor %}</ul>{% endif %}' +
                  '{% if pending_payments %}<h3 style="color:#b45309; margin-top:22px;">Pagamenti da confermare ({{ pending_payments|length }})</h3><ul style="padding-left:20px;">{% for p in pending_payments %}<li><strong>{{ p.contract.sponsor.legal_name }}</strong> · € {{ p.amount_gross|floatformat:2 }} · in attesa da <strong>{{ p.days_pending }} giorni</strong></li>{% endfor %}</ul>{% endif %}' +
                  '{% if failed_emails %}<h3 style="color:#dc2626; margin-top:22px;">Email non recapitate ({{ failed_emails|length }})</h3><ul style="padding-left:20px;">{% for c in failed_emails %}<li>{{ c.subject|truncatechars:60 }} · {{ c.recipients_to.0 }}</li>{% endfor %}</ul>{% endif %}' +
                  btn('{{ admin_url }}', 'Apri il pannello admin') +
                  '<p style="margin-top:20px; color:#6b7280; font-size:13px;">Questa email arriva solo quando ci sono situazioni urgenti.</p>',
            'en': H('⚠ Sponsor Manager alert', '#dc2626') +
                  '<p>Hello {{ user.first_name|default:user.email }},<br>the system detected items requiring attention:</p>' +
                  '{% if overdue_deadlines %}<h3 style="color:#dc2626; margin-top:22px;">Overdue deadlines ({{ overdue_deadlines|length }})</h3><ul style="padding-left:20px;">{% for d in overdue_deadlines %}<li><strong>{{ d.contract.sponsor.legal_name }}</strong> · {{ d.title }} · <strong>{{ d.days_overdue }} days</strong> late</li>{% endfor %}</ul>{% endif %}' +
                  '{% if pending_payments %}<h3 style="color:#b45309; margin-top:22px;">Payments to confirm ({{ pending_payments|length }})</h3><ul style="padding-left:20px;">{% for p in pending_payments %}<li><strong>{{ p.contract.sponsor.legal_name }}</strong> · € {{ p.amount_gross|floatformat:2 }} · pending {{ p.days_pending }} days</li>{% endfor %}</ul>{% endif %}' +
                  '{% if failed_emails %}<h3 style="color:#dc2626; margin-top:22px;">Undelivered emails ({{ failed_emails|length }})</h3><ul style="padding-left:20px;">{% for c in failed_emails %}<li>{{ c.subject|truncatechars:60 }} · {{ c.recipients_to.0 }}</li>{% endfor %}</ul>{% endif %}' +
                  btn('{{ admin_url }}', 'Open the admin panel') +
                  '<p style="margin-top:20px; color:#6b7280; font-size:13px;">This email is only sent when there are urgent items.</p>',
        },
    },
    # 11 ----------------------------------------------------------------
    'password_reset': {
        'subject': {'it': 'Reimposta la password del portale sponsor',
                    'en': 'Reset your sponsor portal password'},
        'body': {
            'it': H('Reimposta la tua password') +
                  '<p>Gentile {{ user.get_full_name|default:user.email }},<br>abbiamo ricevuto una richiesta di reimpostazione della password del tuo accesso al portale.</p>' +
                  btn('{{ reset_url }}', 'Reimposta la password') +
                  '<p style="font-size:13px;">Se il pulsante non funziona, copia questo link:<br><a href="{{ reset_url }}" style="color:inherit; word-break:break-all;">{{ reset_url }}</a></p>' +
                  '<div class="alert-warning"><strong>Non hai richiesto tu il reset?</strong> Ignora questa email: la password resta invariata.</div>' +
                  SIGN_IT,
            'en': H('Reset your password') +
                  '<p>Dear {{ user.get_full_name|default:user.email }},<br>we received a request to reset your sponsor portal password.</p>' +
                  btn('{{ reset_url }}', 'Reset password') +
                  '<p style="font-size:13px;">If the button does not work, copy this link:<br><a href="{{ reset_url }}" style="color:inherit; word-break:break-all;">{{ reset_url }}</a></p>' +
                  '<div class="alert-warning"><strong>Didn\'t request this?</strong> Ignore this email: your password stays the same.</div>' +
                  SIGN_EN,
        },
    },
    # 12 ----------------------------------------------------------------
    'portal_message_notification': {
        'subject': {'it': 'Nuovo messaggio dalla segreteria · {{ event_name }}',
                    'en': 'New message from the secretariat · {{ event_name }}'},
        'body': {
            'it': H('Hai un nuovo messaggio 💬') +
                  '<p>Ciao{% if contact_name %} <strong>{{ contact_name }}</strong>{% endif %},<br>la segreteria organizzativa ti ha inviato un messaggio nel portale sponsor. Ci vuole meno di un minuto per leggerlo.</p>' +
                  btn('{{ messages_url }}', 'Leggi il messaggio →') +
                  '<p style="font-size:13px;">Se il pulsante non funziona, copia questo link:<br><a href="{{ messages_url }}" style="color:#1d6534; word-break:break-all;">{{ messages_url }}</a></p>' +
                  SIGN_IT,
            'en': H('You have a new message 💬') +
                  '<p>Hello{% if contact_name %} <strong>{{ contact_name }}</strong>{% endif %},<br>the organising secretariat sent you a message in the sponsor portal. It takes less than a minute to read.</p>' +
                  btn('{{ messages_url }}', 'Read the message →') +
                  '<p style="font-size:13px;">If the button does not work, copy this link:<br><a href="{{ messages_url }}" style="color:#1d6534; word-break:break-all;">{{ messages_url }}</a></p>' +
                  SIGN_EN,
        },
    },
}


class Command(BaseCommand):
    help = "Popola i 24 Template email (12 punti x ECM/NON_ECM) con testi predefiniti."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Sovrascrive anche i corpi gia' + "'" + ' compilati.')
        parser.add_argument('--attiva', action='store_true',
                            help='Attiva subito i modelli compilati (default: restano NON attivi).')

    def handle(self, *args, **opts):
        from shared.models import EmailTemplate
        force = opts['force']
        attiva = opts['attiva']
        n_fill = 0
        for code, data in TEXTS.items():
            for et in ('ECM', 'NON_ECM'):
                row = EmailTemplate.objects.filter(code=code, event_type=et).first()
                if not row:
                    continue
                has_body = bool((row.body_template or {}).get('it'))
                if has_body and not force:
                    continue
                row.subject_template = data['subject']
                row.body_template = data['body']
                if attiva:
                    row.is_active = True
                row.save(update_fields=['subject_template', 'body_template', 'is_active', 'updated_at'])
                n_fill += 1
        self.stdout.write(self.style.SUCCESS(
            f"Compilati {n_fill} modelli email"
            + (" e ATTIVATI." if attiva else " (restano NON attivi: attivali dall'admin quando vuoi).")
        ))
