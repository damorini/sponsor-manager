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
    email = models.EmailField(
        blank=True, verbose_name="Email",
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

    messages_notify_email = models.EmailField(
        blank=True,
        verbose_name="Email notifiche risposte portale",
        help_text="Indirizzo a cui inviare un avviso quando un cliente risponde "
                  "a un messaggio nel portale. Vuoto = usa l'email della segreteria.",
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

    @property
    def notify_recipient(self):
        """Destinatario degli avvisi (risposte portale): email dedicata se
        impostata, altrimenti l'email della segreteria, altrimenti il supporto."""
        from django.conf import settings
        candidate = (self.messages_notify_email or self.email or
                     getattr(settings, 'SUPPORT_EMAIL', '') or
                     getattr(settings, 'DEFAULT_FROM_EMAIL', ''))
        return (candidate or '').strip()
