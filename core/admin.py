"""
Customizzazione globale dell'admin Django.

Cambia il titolo e l'header del sito admin.
"""
from django.contrib import admin

admin.site.site_header = "Sponsor Manager"
admin.site.site_title = "Sponsor Manager Admin"
admin.site.index_title = "Pannello di gestione"


from django import forms
from django.urls import reverse
from django.utils.html import format_html
from .models import OrganizerSettings, EmailSettings


# =============================================================================
# Registro attività (LogEntry): tutte le modifiche del backoffice, per utente.
# =============================================================================
from django.contrib.admin.models import LogEntry


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    """Sola lettura: registro di tutte le azioni fatte nel backoffice."""
    list_display = ('action_time', 'user', 'content_type', 'oggetto', 'azione', 'dettaglio')
    list_filter = ('action_flag', 'content_type', 'user')
    search_fields = ('object_repr', 'change_message', 'user__email')
    date_hierarchy = 'action_time'
    ordering = ('-action_time',)
    list_select_related = ('user', 'content_type')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # sola consultazione

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Azione')
    def azione(self, obj):
        return {1: 'Creazione', 2: 'Modifica', 3: 'Cancellazione'}.get(
            obj.action_flag, obj.action_flag)

    @admin.display(description='Oggetto')
    def oggetto(self, obj):
        return (obj.object_repr or '')[:60]

    @admin.display(description='Dettaglio')
    def dettaglio(self, obj):
        try:
            return (obj.get_change_message() or '')[:90]
        except Exception:
            return (obj.change_message or '')[:90]


class OrganizerSettingsForm(forms.ModelForm):
    """Editor visuale (TinyMCE) sui testi privacy: grassetto, corsivo, link…"""
    class Meta:
        model = OrganizerSettings
        fields = '__all__'
        widgets = {
            'privacy_short_it': forms.Textarea(attrs={'data-richtext': '1', 'rows': 6}),
            'privacy_short_en': forms.Textarea(attrs={'data-richtext': '1', 'rows': 6}),
            'privacy_policy': forms.Textarea(attrs={'data-richtext': '1', 'rows': 10}),
        }


@admin.register(OrganizerSettings)
class OrganizerSettingsAdmin(admin.ModelAdmin):
    """Pannello unico (singleton) per i dati della segreteria."""
    form = OrganizerSettingsForm

    class Media:
        js = (
            'https://cdn.jsdelivr.net/npm/tinymce@7.6.0/tinymce.min.js',
            'admin/js/richtext.js',
        )
    fieldsets = (
        ("Anagrafica segreteria", {
            "fields": ("name", "address", "email", "phone", "website"),
        }),
        ("Dati fiscali", {
            "fields": ("vat_number", "rea"),
        }),
        ("Logo", {
            "fields": ("logo",),
        }),
        ("Notifiche", {
            "fields": ("messages_notify_email",),
            "description": "Indirizzo che riceve un avviso quando un cliente "
                           "risponde a un messaggio nel portale. Se vuoto, usa "
                           "l'email della segreteria.",
        }),
        ("Privacy (informativa portale)", {
            "fields": ("privacy_policy_version", "privacy_short_it", "privacy_short_en",
                       "privacy_policy"),
            "description": "«Descrizione breve» (IT/EN) è il testo mostrato nella pagina "
                           "di consenso del portale (il testo completo è sul sito). "
                           "Cambiando la versione, ai clienti verrà richiesta di nuovo "
                           "la presa visione al prossimo accesso.",
        }),
        ("Scadenze pagamento (calcolo automatico)", {
            "fields": ("payment_deposit_days_after_signing",
                       "payment_balance_days_before_event"),
            "description": (
                "Regole con cui il sistema calcola le date delle scadenze di "
                "pagamento alla firma del contratto. L'acconto scade questo numero "
                "di giorni DOPO la firma; il saldo questo numero di giorni PRIMA "
                "dell'inizio evento. Sul singolo contratto puoi forzare date "
                "diverse coi campi manuali del Piano pagamento."
            ),
        }),
    )

    def has_add_permission(self, request):
        # Niente "Aggiungi": esiste un solo record.
        return not OrganizerSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Vai dritto alla scheda unica invece della lista.
        obj = OrganizerSettings.load()
        from django.shortcuts import redirect
        url = reverse("admin:core_organizersettings_change", args=[obj.pk])
        return redirect(url)


# Email di PROVA: versione HTML grafica (tema "Houston/spazio", brand verde).
_EMAIL_TEST_HTML = """\
<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#eef2f0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f0;padding:26px 0;">
<tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 10px 34px rgba(13,51,24,.14);">
    <tr><td style="background:linear-gradient(135deg,#1d6534 0%,#0d3318 100%);padding:38px 32px 36px;text-align:center;">
      <div style="display:inline-block;background:#ffffff;border-radius:14px;padding:10px 18px;">
        <img src="cid:valetlogo" alt="VALET Conference" width="150" style="display:block;width:150px;max-width:150px;height:auto;border:0;">
      </div>
      <div style="font-size:42px;line-height:1;margin-top:22px;">&#128640;</div>
      <div style="font-family:Georgia,'Times New Roman',serif;font-size:30px;font-weight:700;color:#ffffff;margin-top:12px;letter-spacing:.3px;">Houston, non abbiamo problemi.</div>
      <div style="height:3px;width:64px;background:#e7cf9b;margin:18px auto 0;border-radius:2px;"></div>
    </td></tr>
    <tr><td style="padding:30px 38px 6px;font-family:Arial,Helvetica,sans-serif;color:#1f2937;font-size:16px;line-height:1.65;">
      <p style="margin:0 0 14px;">Questa e-mail conferma che il sistema di comunicazione del portale <strong style="color:#1d6534;">Sponsor Manager di VALET Conference</strong> funziona perfettamente.</p>
      <p style="margin:0 0 16px;">Sei correttamente raggiungibile: da questo momento riceverai tutte le comunicazioni ufficiali relative alla tua area riservata.</p>
      <p style="margin:0;font-size:19px;font-weight:700;color:#1d6534;">Benvenuto a bordo! &#127881;</p>
      <p style="margin:6px 0 0;color:#6b7280;">Il team VALET CONFERENCE</p>
    </td></tr>
    <tr><td style="padding:6px 38px;"><hr style="border:none;border-top:1px solid #eef0f2;margin:20px 0 16px;"></td></tr>
    <tr><td style="padding:0 38px 30px;font-family:Arial,Helvetica,sans-serif;color:#6b7280;font-size:14px;line-height:1.6;">
      <p style="margin:0 0 8px;font-family:Georgia,'Times New Roman',serif;font-size:18px;font-weight:700;color:#374151;">Houston, we have no problems.</p>
      <p style="margin:0 0 12px;">This e-mail confirms that the communication system of the <strong>Sponsor Manager of VALET Conference</strong> portal is working perfectly. You are correctly reachable: from now on, you will receive all official communications related to your reserved area.</p>
      <p style="margin:0;font-weight:700;color:#374151;">Welcome on board!</p>
      <p style="margin:2px 0 0;">The VALET CONFERENCE Team</p>
    </td></tr>
    <tr><td style="background:#0d3318;padding:16px;text-align:center;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:rgba(255,255,255,.62);">
      VALET Conference &middot; Bologna (ITALY) &middot; helpdesk@valet.it
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""


@admin.register(EmailSettings)
class EmailSettingsAdmin(admin.ModelAdmin):
    """Pannello (singleton) per configurare l'account SMTP di invio email."""
    fieldsets = (
        (None, {
            "fields": ("enabled",),
            "description": "Attiva per inviare le email con i dati SMTP qui sotto. "
                           "Se disattivo, si usano i dati di sistema (.env).",
        }),
        ("Server SMTP", {
            "fields": ("host", "port", ("use_tls", "use_ssl")),
            "description": "Porta 587 con TLS (consigliato) oppure 465 con SSL. "
                           "Spunta una sola tra TLS e SSL.",
        }),
        ("Credenziali", {
            "fields": ("username", "password"),
        }),
        ("Mittente", {
            "fields": ("from_name", "from_email"),
        }),
        ("Test invio", {
            "fields": ("test_recipient",),
            "description": "Indirizzo a cui mandare l'email di PROVA (azione qui sotto). "
                           "Se vuoto, l'email di prova va al tuo indirizzo di accesso.",
        }),
    )
    actions = ["invia_email_di_prova"]

    def has_add_permission(self, request):
        return not EmailSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Invia un'email di PROVA")
    def invia_email_di_prova(self, request, queryset):
        from django.core.mail import EmailMultiAlternatives
        from django.contrib import messages
        from django.contrib.admin import helpers
        from django.template.response import TemplateResponse
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        s = EmailSettings.load()

        # Secondo passo: l'utente ha digitato l'indirizzo e confermato -> invio.
        if request.POST.get('apply_test'):
            dest = (request.POST.get('test_email') or '').strip()
            try:
                validate_email(dest)
            except ValidationError:
                self.message_user(request, "Indirizzo email non valido.", level=messages.ERROR)
                return
            conn = s.get_connection()
            if conn is None:
                self.message_user(
                    request,
                    "Configurazione SMTP non attiva o senza host: spunta «Usa questa "
                    "configurazione SMTP» e compila l'host, poi salva e riprova.",
                    level=messages.WARNING)
                return
            text_body = (
                "Houston, non abbiamo problemi.\n\n"
                "Questa e-mail conferma che il sistema di comunicazione del portale "
                "Sponsor Manager di VALET Conference funziona perfettamente.\n"
                "Sei correttamente raggiungibile: da questo momento riceverai tutte le "
                "comunicazioni ufficiali relative alla tua area riservata.\n\n"
                "Benvenuto a bordo!\nIl team VALET CONFERENCE\n\n"
                "----------------------------------------\n\n"
                "Houston, we have no problems.\n\n"
                "This e-mail confirms that the communication system of the Sponsor Manager "
                "of VALET Conference portal is working perfectly. You are correctly reachable: "
                "from now on, you will receive all official communications related to your "
                "reserved area.\n\nWelcome on board!\nThe VALET CONFERENCE Team"
            )
            html_body = _EMAIL_TEST_HTML
            try:
                msg = EmailMultiAlternatives(
                    subject="🚀 Houston, non abbiamo problemi · VALET Conference",
                    body=text_body,
                    from_email=s.from_full or s.username,
                    to=[dest],
                    connection=conn,
                )
                msg.attach_alternative(html_body, "text/html")
                # Logo VALET incorporato (inline, sempre visibile)
                try:
                    import os
                    from email.mime.image import MIMEImage
                    from django.conf import settings as _st
                    _logo = os.path.join(_st.BASE_DIR, 'core', 'static', 'branding', 'valet_logo.png')
                    if os.path.exists(_logo):
                        with open(_logo, 'rb') as _f:
                            _img = MIMEImage(_f.read(), 'png')
                        _img.add_header('Content-ID', '<valetlogo>')
                        _img.add_header('Content-Disposition', 'inline', filename='valet_logo.png')
                        msg.mixed_subtype = 'related'
                        msg.attach(_img)
                except Exception:
                    pass  # se il logo manca, l'email parte comunque (senza immagine)
                msg.send(fail_silently=False)
                self.message_user(request, f"Email di prova inviata a {dest}. Controlla la casella.",
                                  level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Invio fallito: {e}", level=messages.ERROR)
            return  # torna alla lista

        # Primo passo: chiedo a quale indirizzo inviare (paginetta al volo).
        default = (s.test_recipient or '').strip() or (request.user.email or '')
        ctx = {
            **self.admin_site.each_context(request),
            'title': "Invia un'email di prova",
            'default_email': default,
            'selected': list(queryset.values_list('pk', flat=True)),
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/email_test_confirm.html', ctx)
