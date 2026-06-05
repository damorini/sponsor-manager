"""
Modelli dell'app Events.

Un Event è il contenitore principale di tutto: ogni cosa nel sistema
appartiene a un evento (sponsor possono essere riusati tra eventi, ma
contratti, stand, servizi sono sempre legati a un evento specifico).

Multilingua: i campi name e description sono JSONField con chiavi lingua.
Esempio: {"it": "Congresso", "en": "Congress"}. Usa get_name(language) per
ottenere la traduzione con fallback alla lingua di default dell'evento.
"""
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from datetime import datetime, date
from django.db import models
from django.utils.text import slugify

from core.models import TimeStampedModel


class EventType(models.TextChoices):
    ECM = 'ECM', 'ECM'
    NON_ECM = 'NON_ECM', 'Non ECM'


class EventStatus(models.TextChoices):
    PLANNING = 'planning', 'In pianificazione'
    SELLING = 'selling', 'Vendita aperta'
    CLOSED_SALES = 'closed_sales', 'Vendita chiusa'
    LIVE = 'live', 'In corso'
    ARCHIVED = 'archived', 'Archiviato'


class Language(models.TextChoices):
    """Lingue supportate. Aggiungere qui per estendere."""
    ITALIAN = 'it', 'Italiano'
    ENGLISH = 'en', 'English'


def default_supported_languages():
    """Default per il campo ArrayField supported_languages."""
    return ['it']


class Event(TimeStampedModel):
    """
    Un congresso o evento. Tutto orbita attorno a questa entità.
    """
    slug = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name="Slug",
        help_text="Identificatore breve per URL, es. 'ferrara-cardio-2026'",
    )

    code = models.CharField(
        max_length=12,
        blank=True,
        verbose_name="Sigla evento",
        help_text="Sigla breve per i numeri di contratto, es. 'HIFU'. "
                  "Se vuota, viene generata automaticamente.",
    )

    email_header_image = models.FileField(
        upload_to='events/email_headers/',
        null=True,
        blank=True,
        verbose_name="Header email congresso",
        help_text="Immagine mostrata in cima alle email di questo evento, a tutta larghezza (max 600px). Consigliato PNG/JPG.",
    )

    # Campi multilingua: dict con chiavi lingua
    # Esempio: {"it": "Congresso Cardiologia", "en": "Cardiology Congress"}
    name = models.JSONField(
        verbose_name="Nome (multilingua)",
        help_text='Formato: {"it": "...", "en": "..."}',
    )
    description = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Descrizione (multilingua)",
        help_text='Formato: {"it": "...", "en": "..."}',
    )

    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        verbose_name="Tipo",
    )
    start_date = models.DateField(verbose_name="Data inizio")
    end_date = models.DateField(verbose_name="Data fine")
    location = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Sede",
    )
    venue_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Nome sede",
        help_text="Es. 'Palazzo dei Congressi di Bologna' (usato nei documenti).",
    )
    venue_address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Indirizzo completo sede",
        help_text="Indirizzo completo della venue (es. 'Centro Congressi, Via Roma 1, Bologna')",
    )

    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.PLANNING,
        verbose_name="Stato",
    )

    # Dati ECM-specifici
    ecm_id = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="ID accreditamento Agenas",
        help_text="Solo per eventi ECM (es. '1328')",
    )
    scientific_director = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Responsabile scientifico",
        help_text="Nome completo, es. 'Prof. Mario Rossi'",
    )

    aifa_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Numero riferimento AIFA",
        help_text="Solo per archivio/consultazione interna.",
    )
    medtech_svc_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Numero riferimento MEDTECH/SVC",
        help_text="Solo per archivio/consultazione interna.",
    )

    # Dati per template contratti
    organizer_legal_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Ragione sociale organizzatore",
        help_text="La tua ragione sociale, usata nei contratti",
    )
    contract_signing_location = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Luogo firma contratti",
    )

    notes = models.TextField(blank=True, verbose_name="Note interne")

    # Lingue supportate dall'evento
    supported_languages = ArrayField(
        models.CharField(max_length=2, choices=Language.choices),
        default=default_supported_languages,
        verbose_name="Lingue supportate",
        help_text="Almeno una. Determina cosa gli sponsor vedono nel portale.",
    )
    default_language = models.CharField(
        max_length=2,
        choices=Language.choices,
        default=Language.ITALIAN,
        verbose_name="Lingua di default",
    )

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventi"
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['start_date']),
        ]

    def __str__(self):
        return f"{self.get_name()} ({self.start_date.year})"

    @property
    def is_ecm(self):
        """True se è un evento ECM (per template contratto)."""
        return self.event_type == EventType.ECM

    def clean(self):
        """Valida le date e la coerenza dei campi multilingua."""
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': "La data fine deve essere uguale o successiva alla data inizio.",
            })

        # Il name deve avere almeno la default_language
        if self.name and self.default_language not in self.name:
            raise ValidationError({
                'name': f"Il nome deve includere la lingua di default '{self.default_language}'.",
            })

        # default_language deve essere tra le supported_languages
        if self.default_language and self.default_language not in (self.supported_languages or []):
            raise ValidationError({
                'default_language': "La lingua di default deve essere tra le lingue supportate.",
            })

    def save(self, *args, **kwargs):
        # Genera slug automaticamente
        if not self.slug and self.name:
            base_name = self.get_name(self.default_language or 'it')
            base_slug = slugify(base_name)
            # Converti stringhe a date objects se necessario
            start_date = self.start_date
            if isinstance(start_date, str):
                try:
                    start_date = datetime.fromisoformat(start_date).date()
                except (ValueError, AttributeError):
                    start_date = None
            year = start_date.year if start_date else ''
            self.slug = f"{base_slug}-{year}" if year else base_slug

        # Pulizia sigla evento: niente spazi, sempre MAIUSCOLO
        if self.code:
            self.code = ''.join(self.code.split()).upper()

        super().save(*args, **kwargs)

    # ---------------------------------------------------------------------
    # Helper multilingua
    # ---------------------------------------------------------------------

    def get_name(self, language=None):
        """
        Restituisce il nome nella lingua richiesta, con fallback.
        Ordine: lingua richiesta → default_language → 'it' → prima disponibile.
        """
        return self._get_translated('name', language)

    def get_description(self, language=None):
        """Come get_name ma per description."""
        return self._get_translated('description', language)

    def _get_translated(self, field, language=None):
        """Logica generica di fallback per campi multilingua."""
        value = getattr(self, field) or {}
        if not isinstance(value, dict) or not value:
            return ''

        # Tentativi: lingua richiesta, lingua attiva del portale, default, italiano
        from django.utils.translation import get_language
        for lang in [language, get_language(), self.default_language, 'it']:
            if lang and lang in value and value[lang]:
                return value[lang]

        # Ultimo fallback: prima chiave disponibile
        return next(iter(value.values()), '')

    @property
    def is_active(self):
        return self.status != EventStatus.ARCHIVED
