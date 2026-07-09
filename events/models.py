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
    cancellation_penalty_percent = models.PositiveSmallIntegerField(
        default=50,
        verbose_name="Penale cancellazione (%)",
        help_text="Percentuale dell'importo totale trattenuta come penale in caso di rinuncia entro 30 gg. "
                  "Appare nei Termini di cancellazione del contratto.",
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

    # Indirizzi in copia nascosta (BCC) a cui inoltrare AUTOMATICAMENTE ogni email
    # inviata per questo evento (es. una casella interna di monitoraggio).
    notification_cc_emails = models.TextField(
        blank=True,
        verbose_name="Email in copia (inoltro automatico)",
        help_text="Indirizzi a cui inoltrare in copia (BCC) tutte le email inviate "
                  "per questo evento. Uno per riga oppure separati da virgola. "
                  "Lo sponsor non li vede.",
    )

    # Segreteria Scientifica: dati liberi + logo, stampati in basso a destra
    # nel PDF del preventivo (la Segreteria Organizzativa va a sinistra).
    scientific_secretariat = models.TextField(
        blank=True,
        verbose_name="Segreteria Scientifica (dati per il preventivo)",
        help_text="Testo libero con tutti i dati della segreteria scientifica "
                  "(nome, indirizzo, contatti...). Appare in basso a destra nel "
                  "PDF del preventivo. Lascia vuoto per non mostrarla.",
    )
    scientific_secretariat_logo = models.FileField(
        upload_to='events/scientific_secretariat/',
        null=True,
        blank=True,
        verbose_name="Logo Segreteria Scientifica",
        help_text="Logo mostrato accanto ai dati della segreteria scientifica "
                  "nel PDF del preventivo (consigliato PNG/JPG).",
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

    @property
    def luogo_completo(self):
        """Luogo dell'evento come 'Nome sede, Indirizzo, Città', saltando i vuoti
        ed evitando duplicati. Da usare OVUNQUE si cita la sede (portale,
        preventivo, contratto, email): così l'indirizzo compare sempre quando
        valorizzato. Se manca 'Indirizzo completo sede' sull'evento, mostra ciò
        che c'è (nome sede e/o città)."""
        parts = []
        for v in (self.venue_name, self.venue_address, self.location):
            v = " ".join(str(v or "").split()).strip()
            if v and not any(v.lower() in p.lower() or p.lower() in v.lower() for p in parts):
                parts.append(v)
        return ", ".join(parts)

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

        # Rileva il passaggio -> ARCHIVIATO per chiudere le scadenze aperte.
        era_archiviato = False
        if self.pk:
            era_archiviato = (
                type(self).objects
                .filter(pk=self.pk)
                .values_list('status', flat=True)
                .first() == EventStatus.ARCHIVED
            )

        super().save(*args, **kwargs)

        if self.status == EventStatus.ARCHIVED and not era_archiviato:
            self.chiudi_scadenze_aperte()
            self.archivia_messaggi_portale()

    def archivia_messaggi_portale(self):
        """Evento archiviato: sposta i messaggi del portale di questo evento
        nell'archivio messaggi (non li cancella)."""
        from sponsors.models import PortalMessage
        from django.utils import timezone
        return PortalMessage.objects.filter(
            event=self, archived_at__isnull=True,
        ).update(archived_at=timezone.now())

    def chiudi_scadenze_aperte(self):
        """Evento archiviato: annulla (WAIVED) le scadenze ancora aperte dei
        suoi contratti, così non risultano 'da fare' nel portale e non partono
        più i reminder. Storico preservato (non vengono cancellate fisicamente)."""
        from contracts.models import Deadline, DeadlineStatus
        aperte = [
            DeadlineStatus.PENDING,
            DeadlineStatus.REMINDER_SENT,
            DeadlineStatus.OVERDUE,
        ]
        return Deadline.objects.filter(
            contract__event=self,
            status__in=aperte,
        ).update(status=DeadlineStatus.WAIVED)

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


class PromotionalCampaign(TimeStampedModel):
    """
    Campagna email ricorrente per proporre servizi extra/visibilità agli
    sponsor già confermati di un evento (es. "abbiamo pensato a numerosi
    servizi per aumentare la vostra visibilità..."). Un task schedulato la
    rimanda ogni `interval_days` giorni finché resta attiva.
    """
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='promotional_campaigns',
        verbose_name="Evento",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Nome interno",
        help_text="Solo per riconoscerla in lista: il cliente non la vede.",
    )
    subject = models.JSONField(
        default=dict, blank=True, verbose_name="Oggetto",
        help_text="Bilingue IT/EN.",
    )
    body = models.JSONField(
        default=dict, blank=True, verbose_name="Corpo email",
        help_text="Bilingue IT/EN. Segnaposto: {{ sponsor.legal_name }}, {{ event_name }}, {{ contact.full_name }}.",
    )
    interval_days = models.PositiveIntegerField(
        default=14,
        verbose_name="Ogni quanti giorni",
        help_text="Intervallo minimo tra un invio e il successivo.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Attiva")
    last_sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Ultimo invio")

    class Meta:
        verbose_name = "Campagna promozionale"
        verbose_name_plural = "Campagne promozionali"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} · {self.event}"

    @property
    def is_due(self):
        """True se attiva e se e' passato almeno interval_days dall'ultimo invio."""
        if not self.is_active:
            return False
        if self.last_sent_at is None:
            return True
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() - self.last_sent_at >= timedelta(days=self.interval_days)

    def eligible_contacts_queryset(self):
        """Contatti con email di sponsor CONFERMATI (contratto principale
        firmato/attivo/completato) dell'evento, esclusi quelli disiscritti
        da QUESTA campagna. Contract.objects esclude gia' i contratti nel
        cestino; qui si esclude anche lo sponsor nel cestino per sicurezza."""
        from contracts.models import Contract, ContractKind, ContractStatus
        from sponsors.models import Contact

        sponsor_ids = (Contract.objects
                       .filter(event=self.event, contract_kind=ContractKind.MAIN,
                               status__in=[ContractStatus.SIGNED,
                                           ContractStatus.ACTIVE,
                                           ContractStatus.COMPLETED])
                       .values_list('sponsor_id', flat=True).distinct())
        opted_out_ids = self.opt_outs.values_list('contact_id', flat=True)
        return (Contact.objects
                .filter(sponsor_id__in=sponsor_ids, sponsor__deleted_at__isnull=True)
                .exclude(email='')
                .exclude(id__in=opted_out_ids))


class PromotionalCampaignOptOut(TimeStampedModel):
    """
    Un contatto disiscritto da UNA campagna promozionale specifica: non
    riceve piu' QUEL tipo di messaggio, ma resta raggiungibile per contratti,
    scadenze e altre comunicazioni transazionali.
    """
    campaign = models.ForeignKey(
        PromotionalCampaign,
        on_delete=models.CASCADE,
        related_name='opt_outs',
        verbose_name="Campagna",
    )
    contact = models.ForeignKey(
        'sponsors.Contact',
        on_delete=models.CASCADE,
        related_name='campaign_opt_outs',
        verbose_name="Contatto",
    )

    class Meta:
        verbose_name = "Disiscrizione campagna"
        verbose_name_plural = "Disiscrizioni campagne"
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'contact'],
                name='unique_promocampaign_optout_campaign_contact',
            ),
        ]

    def __str__(self):
        return f"{self.contact} · {self.campaign}"
