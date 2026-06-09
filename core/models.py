"""
Modelli base condivisi da tutta l'applicazione.

Centralizzano pattern ricorrenti come timestamp, soft delete e UUID primary key.
Tutti i modelli di dominio ereditano da TimeStampedModel come minimo.
"""
import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Modello base che fornisce:
    - UUID come primary key (più sicuro di ID sequenziali)
    - created_at: data creazione, immutabile
    - updated_at: data ultima modifica, aggiornata automaticamente
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Creato il",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Modificato il",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet che esclude record soft-deleted di default."""

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """Manager che mostra solo record non cancellati."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    """Manager che mostra TUTTI i record, anche cancellati. Per uso admin."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(TimeStampedModel):
    """
    Aggiunge soft delete: cancellare un record non lo rimuove fisicamente,
    ma valorizza deleted_at. Le query normali lo nascondono.
    
    Per recuperare i cancellati: Model.all_objects.dead()
    Per query su tutto: Model.all_objects.all()
    """
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Cancellato il",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard=False):
        """
        Override del delete: di default fa soft delete.
        Per cancellare davvero: instance.delete(hard=True)
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at', 'updated_at'])

    def restore(self):
        """Annulla il soft delete."""
        self.deleted_at = None
        self.save(update_fields=['deleted_at', 'updated_at'])


def _split_emails(value):
    """Spezza una stringa di email separate da ; o , in lista pulita."""
    import re
    return [e.strip() for e in re.split(r'[;,]', value or '') if e.strip()]


def _validate_email_list(value):
    """Valida una stringa con uno o più indirizzi (separatori ; o ,)."""
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    bad = []
    for e in _split_emails(value):
        try:
            validate_email(e)
        except ValidationError:
            bad.append(e)
    if bad:
        raise ValidationError("Indirizzi email non validi: " + ", ".join(bad))


class OrganizerSettings(models.Model):
    """
    Impostazioni della segreteria organizzativa (singleton: un solo record).
    Usate nel footer di tutte le email. Modificabili dall'admin.
    """
    name = models.CharField(
        max_length=200, blank=True, verbose_name="Nome segreteria",
    )
    address = models.TextField(
        blank=True, verbose_name="Indirizzo",
    )
    email = models.CharField(
        max_length=500, blank=True, verbose_name="Email",
        validators=[_validate_email_list],
        help_text="Uno o più indirizzi separati da ; (o ,).",
    )
    phone = models.CharField(
        max_length=50, blank=True, verbose_name="Telefono",
    )
    website = models.CharField(
        max_length=200, blank=True, verbose_name="Sito internet",
    )
    vat_number = models.CharField(
        max_length=30, blank=True, verbose_name="P.IVA",
    )
    rea = models.CharField(
        max_length=30, blank=True, verbose_name="REA",
    )
    logo = models.FileField(
        upload_to='organizer/', null=True, blank=True,
        verbose_name="Logo segreteria",
        help_text="Logo mostrato nel footer delle email.",
    )

    messages_notify_email = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Email notifiche risposte portale",
        validators=[_validate_email_list],
        help_text="Uno o più indirizzi separati da ; (o ,) a cui inviare l'avviso "
                  "quando un cliente risponde a un messaggio nel portale. "
                  "Vuoto = usa l'email della segreteria.",
    )

    # --- Informativa privacy mostrata nel portale ---
    privacy_short_it = models.TextField(
        blank=True,
        verbose_name="Descrizione breve (IT)",
        help_text="Testo breve mostrato nella pagina di consenso del portale "
                  "(italiano). Il testo completo è sul sito.",
    )
    privacy_short_en = models.TextField(
        blank=True,
        verbose_name="Descrizione breve (EN)",
        help_text="Versione inglese della descrizione breve. Vuoto = usa l'italiano.",
    )
    privacy_policy = models.TextField(
        blank=True,
        verbose_name="Informativa privacy (testo)",
        help_text="Testo dell'informativa mostrato nel portale. Vuoto = testo "
                  "segnaposto. Consigliato farlo validare da un consulente.",
    )
    privacy_policy_version = models.CharField(
        max_length=20, default='1.0',
        verbose_name="Versione informativa",
        help_text="Cambia la versione quando aggiorni l'informativa: ai clienti "
                  "verrà richiesta di nuovo l'accettazione al prossimo accesso.",
    )

    # Piano pagamento (acconto/saldo)
    payment_deposit_days_after_signing = models.IntegerField(
        default=0,
        verbose_name="Giorni scadenza acconto (dopo firma)",
        help_text="L'acconto scade questo numero di giorni dopo la firma del contratto.",
    )
    payment_balance_days_before_event = models.IntegerField(
        default=0,
        verbose_name="Giorni scadenza saldo (prima evento)",
        help_text="Il saldo scade questo numero di giorni prima dell'inizio dell'evento.",
    )

    class Meta:
        verbose_name = "Impostazioni segreteria"
        verbose_name_plural = "Impostazioni segreteria"

    def __str__(self):
        return self.name or "Impostazioni segreteria"

    def save(self, *args, **kwargs):
        # Singleton: forza sempre pk=1, esiste un solo record.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Restituisce l'unico record, creandolo vuoto se non esiste."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def privacy_short(self, lang='it'):
        """Descrizione breve privacy nella lingua richiesta (EN con fallback IT)."""
        if str(lang or '').startswith('en') and (self.privacy_short_en or '').strip():
            return self.privacy_short_en.strip()
        return (self.privacy_short_it or '').strip()

    def notify_recipients(self):
        """LISTA dei destinatari degli avvisi (risposte portale): uno o più
        indirizzi dedicati, altrimenti l'email della segreteria/supporto."""
        from django.conf import settings
        dedicati = _split_emails(self.messages_notify_email)
        if dedicati:
            return dedicati
        org = _split_emails(self.email)
        if org:
            return org
        single = (getattr(settings, 'SUPPORT_EMAIL', '') or
                  getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
        return [single] if single else []

    @property
    def notify_recipient(self):
        """Primo destinatario (compatibilità). Preferire notify_recipients()."""
        lst = self.notify_recipients()
        return lst[0] if lst else ''


class EmailSettings(models.Model):
    """Configurazione SMTP della casella da cui partono le email (singleton).

    Se 'enabled' è attivo e c'è un host, le email usano questi dati invece di
    quelli di sistema (.env / settings).
    """
    enabled = models.BooleanField(
        default=False, verbose_name="Usa questa configurazione SMTP",
        help_text="Se attivo, le email vengono inviate con i dati qui sotto. "
                  "Se disattivo, si usano i dati di sistema (.env).",
    )
    host = models.CharField(
        max_length=200, blank=True, verbose_name="Server SMTP (host)",
        help_text="Es. smtp.gmail.com, smtp.aruba.it, ...",
    )
    port = models.IntegerField(default=587, verbose_name="Porta",
                               help_text="587 (TLS) oppure 465 (SSL).")
    username = models.CharField(max_length=200, blank=True, verbose_name="Utente",
                                help_text="Di solito l'indirizzo email completo.")
    password = models.CharField(
        max_length=255, blank=True, verbose_name="Password",
        help_text="Password della casella o password per app (es. Gmail).",
    )
    use_tls = models.BooleanField(default=True, verbose_name="Usa TLS (porta 587)")
    use_ssl = models.BooleanField(default=False, verbose_name="Usa SSL (porta 465)")
    from_email = models.EmailField(
        blank=True, verbose_name="Mittente (from)",
        help_text="Indirizzo che appare come mittente. Vuoto = usa l'utente.",
    )
    from_name = models.CharField(
        max_length=120, blank=True, verbose_name="Nome mittente",
        help_text="Es. «Segreteria VALET». Opzionale.",
    )
    test_recipient = models.EmailField(
        blank=True, verbose_name="Email per il test",
        help_text="Indirizzo a cui inviare l'email di PROVA. "
                  "Vuoto = la tua email di accesso.",
    )

    class Meta:
        verbose_name = "Configurazione email (SMTP)"
        verbose_name_plural = "Configurazione email (SMTP)"

    def __str__(self):
        return f"SMTP {self.host}" if self.host else "Configurazione email (SMTP)"

    def save(self, *args, **kwargs):
        self.pk = 1  # singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def from_full(self):
        """Mittente completo 'Nome <email>' per le email."""
        addr = (self.from_email or self.username or '').strip()
        if self.from_name and addr:
            return f"{self.from_name} <{addr}>"
        return addr

    def get_connection(self):
        """Connessione email Django dai dati SMTP, o None se non configurata."""
        if not (self.enabled and self.host):
            return None
        from django.core.mail import get_connection
        return get_connection(
            backend='django.core.mail.backends.smtp.EmailBackend',
            host=self.host, port=self.port,
            username=self.username, password=self.password,
            use_tls=self.use_tls, use_ssl=self.use_ssl,
            timeout=15,  # non lasciare appesa la richiesta se la porta e' bloccata
        )
