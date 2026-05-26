"""
Modelli condivisi: documenti, comunicazioni, audit log, template email.

Document e Communication usano relazioni "polymorphic" via ContentType,
che permettono di legare un record a qualsiasi entità (Contract, Sponsor,
Event, Deadline) senza tabelle di join separate.
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import SoftDeleteModel, TimeStampedModel


# =============================================================================
# DOCUMENT
# =============================================================================

class DocumentType(models.TextChoices):
    CONTRACT_PDF = 'contract_pdf', 'Contratto PDF'
    QUOTE = 'quote', 'Preventivo'
    SIGNED_CONTRACT = 'signed_contract', 'Contratto firmato'
    INVOICE = 'invoice', 'Fattura'
    LOGO = 'logo', 'Logo'
    ADV_MATERIAL = 'adv_material', 'Materiale ADV'
    WORKSHOP_ABSTRACT = 'workshop_abstract', 'Abstract workshop'
    COMPLIANCE_AIFA = 'compliance_aifa', 'Compliance AIFA'
    STAND_PLAN = 'stand_plan', 'Scheda stand'
    EVENT_FLOORPLAN = 'event_floorplan', 'Planimetria evento'
    OTHER = 'other', 'Altro'


class StorageProvider(models.TextChoices):
    S3 = 's3', 'AWS S3'
    R2 = 'r2', 'Cloudflare R2'
    LOCAL = 'local', 'Locale'


class Document(SoftDeleteModel):
    """
    Documento collegato a un'entità qualsiasi (Contract, Sponsor, Event, Deadline).
    Il file vero sta su storage esterno (S3/R2); qui solo il riferimento.
    
    Esempi d'uso:
    - PDF contratto generato → linkato al Contract
    - Logo sponsor caricato → linkato allo Sponsor
    - Planimetria fiera → linkata all'Event
    - Materiali ADV ricevuti → linkati alla Deadline
    """
    # Polymorphic relationship via ContentType framework di Django
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Tipo entità",
    )
    object_id = models.UUIDField(verbose_name="ID entità")
    entity = GenericForeignKey('content_type', 'object_id')

    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
        verbose_name="Tipo documento",
    )
    title = models.CharField(max_length=255, verbose_name="Titolo")
    description = models.TextField(blank=True, verbose_name="Descrizione")

    # Riferimento file
    storage_url = models.URLField(
        max_length=1000,
        verbose_name="URL storage",
    )
    storage_provider = models.CharField(
        max_length=20,
        choices=StorageProvider.choices,
        default=StorageProvider.S3,
        verbose_name="Provider storage",
    )
    file_name = models.CharField(max_length=255, verbose_name="Nome file")
    file_size_bytes = models.BigIntegerField(null=True, blank=True, verbose_name="Dimensione (byte)")
    mime_type = models.CharField(max_length=100, blank=True, verbose_name="MIME type")

    # Versioning leggero
    version = models.IntegerField(default=1, verbose_name="Versione")
    superseded_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supersedes',
        verbose_name="Sostituito da",
    )

    # Chi ha caricato
    uploaded_by_user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
        verbose_name="Caricato da utente",
    )
    uploaded_by_contact = models.ForeignKey(
        'sponsors.Contact',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_documents',
        verbose_name="Caricato da contatto",
    )

    is_visible_to_sponsor = models.BooleanField(
        default=True,
        verbose_name="Visibile a sponsor",
        help_text="Se False, è un documento solo interno",
    )

    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documenti"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['document_type']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()})"

    @property
    def is_current_version(self):
        return self.superseded_by is None


# =============================================================================
# EMAIL TEMPLATE
# =============================================================================

class CommunicationType(models.TextChoices):
    INITIAL_SEND = 'initial_send', 'Invio iniziale contratto'
    REMINDER = 'reminder', 'Reminder scadenza'
    OVERDUE_ALERT = 'overdue_alert', 'Sollecito ritardo'
    THANK_YOU = 'thank_you', 'Ringraziamento'
    DOCUMENT_REQUEST = 'document_request', 'Richiesta documenti'
    MANUAL = 'manual', 'Manuale'


class EmailTemplate(TimeStampedModel):
    """
    Template email modificabili dal backoffice senza touchare il codice.
    Placeholder Django/Jinja2: {{ sponsor.legal_name }}, {{ event.name }}, etc.
    """
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Codice",
        help_text="Es. 'contract_initial_send', 'deadline_reminder_t10'",
    )
    name = models.CharField(max_length=255, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrizione")

    communication_type = models.CharField(
        max_length=50,
        choices=CommunicationType.choices,
        verbose_name="Tipo comunicazione",
    )

    subject_template = models.CharField(
        max_length=500,
        verbose_name="Oggetto (template)",
        help_text="Supporta placeholder {{ var }}",
    )
    body_template = models.TextField(
        verbose_name="Corpo (template)",
        help_text="Supporta placeholder {{ var }}",
    )

    language = models.CharField(
        max_length=2,
        default='it',
        verbose_name="Lingua",
    )
    is_active = models.BooleanField(default=True, verbose_name="Attivo")

    class Meta:
        verbose_name = "Template email"
        verbose_name_plural = "Template email"
        ordering = ['code']

    def __str__(self):
        return self.name


# =============================================================================
# COMMUNICATION
# =============================================================================

class CommunicationChannel(models.TextChoices):
    EMAIL = 'email', 'Email'
    PHONE = 'phone', 'Telefono'
    MEETING = 'meeting', 'Meeting'
    NOTE = 'note', 'Nota'


class CommunicationStatus(models.TextChoices):
    DRAFT = 'draft', 'Bozza'
    QUEUED = 'queued', 'In coda'
    SENT = 'sent', 'Inviata'
    DELIVERED = 'delivered', 'Consegnata'
    OPENED = 'opened', 'Aperta'
    CLICKED = 'clicked', 'Cliccata'
    BOUNCED = 'bounced', 'Bounced'
    FAILED = 'failed', 'Fallita'


class Communication(TimeStampedModel):
    """
    Log di tutte le comunicazioni: email inviate, telefonate, meeting, note.
    Polymorphic come Document, può essere agganciata a qualsiasi entità.
    """
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Tipo entità",
    )
    object_id = models.UUIDField(verbose_name="ID entità")
    entity = GenericForeignKey('content_type', 'object_id')

    channel = models.CharField(
        max_length=20,
        choices=CommunicationChannel.choices,
        default=CommunicationChannel.EMAIL,
        verbose_name="Canale",
    )
    communication_type = models.CharField(
        max_length=50,
        choices=CommunicationType.choices,
        verbose_name="Tipo",
    )

    # Destinatari (array per supportare multi-destinatario)
    recipients_to = ArrayField(
        models.EmailField(),
        default=list,
        blank=True,
        verbose_name="Destinatari (To)",
    )
    recipients_cc = ArrayField(
        models.EmailField(),
        default=list,
        blank=True,
        verbose_name="Destinatari (CC)",
    )
    recipients_bcc = ArrayField(
        models.EmailField(),
        default=list,
        blank=True,
        verbose_name="Destinatari (BCC)",
    )

    subject = models.CharField(max_length=500, blank=True, verbose_name="Oggetto")
    body_text = models.TextField(blank=True, verbose_name="Corpo testuale")
    body_html = models.TextField(blank=True, verbose_name="Corpo HTML")

    attachment_document_ids = ArrayField(
        models.UUIDField(),
        default=list,
        blank=True,
        verbose_name="Allegati (Document IDs)",
    )

    status = models.CharField(
        max_length=20,
        choices=CommunicationStatus.choices,
        default=CommunicationStatus.QUEUED,
        verbose_name="Stato",
    )

    # Tracking provider esterno
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="ID messaggio provider",
    )
    provider_response = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Risposta provider",
    )

    # Timestamps tracking
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Inviata il")
    delivered_at = models.DateTimeField(null=True, blank=True)
    first_opened_at = models.DateTimeField(null=True, blank=True)
    open_count = models.IntegerField(default=0, verbose_name="N. aperture")
    bounced_at = models.DateTimeField(null=True, blank=True)
    bounce_reason = models.TextField(blank=True)

    # Origine
    triggered_by_user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Inviata da utente",
    )
    is_automated = models.BooleanField(
        default=False,
        verbose_name="Automatica",
        help_text="True se inviata da automazione, False se manuale",
    )

    class Meta:
        verbose_name = "Comunicazione"
        verbose_name_plural = "Comunicazioni"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status']),
            models.Index(fields=['provider_message_id']),
        ]

    def __str__(self):
        return f"{self.get_communication_type_display()} · {self.subject[:50]}"


# =============================================================================
# INVOICE EXPORT
# =============================================================================

class InvoiceExportType(models.TextChoices):
    FULL = 'full', 'Totale'
    DEPOSIT = 'deposit', 'Acconto'
    BALANCE = 'balance', 'Saldo'
    INSTALLMENT = 'installment', 'Rata'
    CREDIT_NOTE = 'credit_note', 'Nota credito'


class InvoiceExportStatus(models.TextChoices):
    PENDING_EXPORT = 'pending_export', 'Da esportare'
    EXPORTED = 'exported', 'Esportato'
    INVOICED = 'invoiced', 'Fatturato'
    PAID = 'paid', 'Pagato'
    CANCELLED = 'cancelled', 'Annullato'


class InvoiceExport(TimeStampedModel):
    """
    Tracciamento delle fatture esportate verso sistema esterno (Fatture in Cloud,
    Aruba, etc.). Non emette fatture, solo registra cosa hai già passato al
    sistema di fatturazione esterno per evitare duplicati.
    """
    contract = models.ForeignKey(
        'contracts.Contract',
        on_delete=models.PROTECT,
        related_name='invoice_exports',
        verbose_name="Contratto",
    )

    export_type = models.CharField(
        max_length=30,
        choices=InvoiceExportType.choices,
        default=InvoiceExportType.FULL,
        verbose_name="Tipo export",
    )
    installment_number = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Numero rata",
    )

    # Importi (può essere parziale del contratto)
    amount_subtotal = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Imponibile",
    )
    amount_vat = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        verbose_name="IVA",
    )
    amount_total = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name="Totale",
    )

    # Riferimenti sistema esterno
    external_system = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Sistema esterno",
        help_text="Es. fattureincloud, aruba, fatel, manual",
    )
    external_invoice_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Numero fattura esterna",
    )
    external_invoice_date = models.DateField(
        null=True, blank=True,
        verbose_name="Data fattura esterna",
    )
    external_reference_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID riferimento esterno",
    )

    status = models.CharField(
        max_length=20,
        choices=InvoiceExportStatus.choices,
        default=InvoiceExportStatus.PENDING_EXPORT,
        verbose_name="Stato",
    )

    exported_at = models.DateTimeField(null=True, blank=True)
    invoiced_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Snapshot dati fiscali al momento dell'export
    fiscal_data_snapshot = models.JSONField(
        verbose_name="Snapshot dati fiscali",
        help_text="Dati sponsor congelati al momento dell'export",
    )

    export_file_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="URL file export",
    )

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Export fattura"
        verbose_name_plural = "Export fatture"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['contract', 'export_type', 'installment_number'],
                name='invoice_export_unique_installment',
            ),
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['external_invoice_number']),
        ]

    def __str__(self):
        ref = self.external_invoice_number or self.contract.contract_number
        return f"{ref} · {self.amount_total}€"


# =============================================================================
# AUDIT LOG
# =============================================================================

class AuditLog(models.Model):
    """
    Log di operazioni critiche per tracciabilità.
    Non eredita da TimeStampedModel: ha solo created_at, mai modificato.
    """
    import uuid as uuid_module

    id = models.UUIDField(
        primary_key=True,
        default=uuid_module.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(
        max_length=50,
        verbose_name="Azione",
        help_text="Es. create, update, delete, status_change, login",
    )
    entity_type = models.CharField(max_length=50, verbose_name="Tipo entità")
    entity_id = models.UUIDField(null=True, blank=True, verbose_name="ID entità")

    changes = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Modifiche",
        help_text="Es. {\"status\": {\"from\": \"draft\", \"to\": \"sent\"}}",
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.action} · {self.entity_type} · {self.created_at}"



class LetterTemplate(TimeStampedModel):
    """Template lettere riutilizzabili (preventivi, rettifiche, ecc).
    Segnaposti corpo: {{ azienda }} {{ evento }} {{ date_evento }}
    {{ luogo_evento }} {{ numero }} {{ totale }} {{ stand }} {{ servizi }}"""
    name = models.CharField(max_length=255, verbose_name="Nome",
        help_text="Es. 'Preventivo iniziale', 'Rettifica', 'Invio documenti'")
    body_template = models.TextField(verbose_name="Corpo lettera (template)",
        help_text="Segnaposti: {{ azienda }}, {{ evento }}, {{ date_evento }}, "
                  "{{ luogo_evento }}, {{ numero }}, {{ totale }}, {{ stand }}, {{ servizi }}")
    language = models.CharField(max_length=2, default='it', verbose_name="Lingua")
    is_active = models.BooleanField(default=True, verbose_name="Attivo")

    class Meta:
        verbose_name = "Template lettera"
        verbose_name_plural = "Template lettere"
        ordering = ['name']

    def __str__(self):
        return self.name
