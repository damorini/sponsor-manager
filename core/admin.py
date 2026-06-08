"""
Customizzazione globale dell'admin Django.

Cambia il titolo e l'header del sito admin.
"""
from django.contrib import admin

admin.site.site_header = "Sponsor Manager"
admin.site.site_title = "Sponsor Manager Admin"
admin.site.index_title = "Pannello di gestione"


from django.urls import reverse
from django.utils.html import format_html
from .models import OrganizerSettings, EmailSettings


@admin.register(OrganizerSettings)
class OrganizerSettingsAdmin(admin.ModelAdmin):
    """Pannello unico (singleton) per i dati della segreteria."""
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
            "fields": ("privacy_policy_version", "privacy_policy"),
            "description": "Testo dell'informativa mostrata nel portale e versione. "
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
    )
    actions = ["invia_email_di_prova"]

    def has_add_permission(self, request):
        return not EmailSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Invia un'email di PROVA al tuo indirizzo")
    def invia_email_di_prova(self, request, queryset):
        from django.core.mail import EmailMultiAlternatives
        from django.contrib import messages
        s = EmailSettings.load()
        dest = request.user.email
        if not dest:
            self.message_user(request, "Il tuo utente non ha un'email impostata.",
                              level=messages.ERROR)
            return
        conn = s.get_connection()
        if conn is None:
            self.message_user(
                request,
                "Configurazione SMTP non attiva o senza host: spunta «Usa questa "
                "configurazione SMTP» e compila l'host, poi salva e riprova.",
                level=messages.WARNING)
            return
        try:
            msg = EmailMultiAlternatives(
                subject="Email di prova · Sponsor Manager",
                body="Se leggi questo messaggio, la configurazione SMTP funziona. 👍",
                from_email=s.from_full or s.username,
                to=[dest],
                connection=conn,
            )
            msg.send(fail_silently=False)
            self.message_user(request, f"Email di prova inviata a {dest}. Controlla la casella.",
                              level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Invio fallito: {e}", level=messages.ERROR)
