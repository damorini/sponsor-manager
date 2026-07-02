"""
Admin per app shared: Document, Communication, EmailTemplate,
InvoiceExport, AuditLog.

EmailTemplate ha widget multilingua per subject e body.
"""
from django import forms
from django.contrib import admin
from core.admin_filters import evento_filter
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.html import format_html

from core.admin_widgets import TranslatableJSONField

from .models import (
    AuditLog, Communication, CommunicationStatus, Document, DocumentType,
    EmailTemplate, InvoiceExport, InvoiceExportStatus, LetterTemplate,
)


# =============================================================================
# DOCUMENT
# =============================================================================

def _store_uploaded_document(doc, f):
    """Salva il file caricato su storage e popola i riferimenti del Document."""
    from django.conf import settings
    from django.core.files.storage import default_storage
    model = doc.content_type.model if doc.content_type_id else 'misc'
    rel = f"documents/{model}/{doc.object_id}/{f.name}"
    saved = default_storage.save(rel, f)
    doc.storage_url = settings.MEDIA_URL + saved
    doc.file_name = f.name
    doc.file_size_bytes = getattr(f, 'size', None)
    doc.mime_type = getattr(f, 'content_type', '') or ''
    doc.storage_provider = 'local'
    if not doc.title:
        doc.title = f.name


class DocumentUploadForm(forms.ModelForm):
    """Form Document con CARICAMENTO file: l'operatore allega un PDF e
    URL/nome/dimensione si compilano da soli (niente più URL a mano)."""
    upload = forms.FileField(
        required=False, label="Carica file",
        help_text="Allega un PDF: URL, nome e dimensione si compilano da soli.",
    )

    class Meta:
        model = Document
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Con l'upload questi non sono più obbligatori a mano.
        for f in ('storage_url', 'file_name'):
            if f in self.fields:
                self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        # OK se: carichi un nuovo file, indichi un URL, oppure il documento ha
        # GIA' un file salvato (es. PDF preventivo gia' allegato: modificando
        # altre parti del contratto non si deve ricaricare il file).
        has_existing = bool((getattr(self.instance, 'storage_url', '') or '').strip())
        if (not cleaned.get('upload') and not cleaned.get('storage_url')
                and not has_existing):
            raise forms.ValidationError("Carica un file oppure indica un URL.")
        return cleaned


from django.contrib.contenttypes.admin import GenericTabularInline


class ContractDocumentInline(GenericTabularInline):
    """Documenti allegati al contratto (fatture, allegati vari) con upload file.
    Spunta 'Visibile a sponsor' per farli vedere al cliente nel portale."""
    model = Document
    form = DocumentUploadForm
    ct_field = 'content_type'
    ct_fk_field = 'object_id'
    extra = 0
    fields = ('document_type', 'title', 'upload', 'is_visible_to_sponsor', 'apri_file')
    readonly_fields = ('apri_file',)
    verbose_name = 'Documento'
    verbose_name_plural = 'Documenti / Fatture (spunta "Visibile a sponsor" per il portale)'

    @admin.display(description='File')
    def apri_file(self, obj):
        if obj and obj.pk and obj.storage_url:
            url = reverse('core:documento_apri', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">📄 apri</a>', url)
        return '—'


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentUploadForm

    def get_queryset(self, request):
        from core.event_scope import scope_generic_by_event
        return scope_generic_by_event(request, super().get_queryset(request))

    def save_model(self, request, obj, form, change):
        f = form.cleaned_data.get('upload')
        if f:
            _store_uploaded_document(obj, f)
        if obj.uploaded_by_user_id is None:
            obj.uploaded_by_user = request.user
        super().save_model(request, obj, form, change)


    list_display = (
        'title', 'type_badge', 'entity_display',
        'file_name', 'file_size_display', 'uploaded_by_display',
        'is_visible_to_sponsor', 'created_at_short', 'apri_file',
    )
    list_filter = ('document_type', 'storage_provider', 'is_visible_to_sponsor')
    search_fields = ('title', 'file_name', 'description')
    list_select_related = ('content_type', 'uploaded_by_user', 'uploaded_by_contact')
    readonly_fields = (
        'created_at', 'updated_at',
        'file_size_bytes', 'mime_type', 'apri_file',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('document_type', 'title', 'description'),
        }),
        ('Riferimento entità', {
            'fields': ('content_type', 'object_id'),
            'description': "Tipo entità + ID entità (Contract, Sponsor, Event, Deadline)",
        }),
        ('File', {
            'fields': ('upload', 'storage_url', 'storage_provider', 'file_name',
                       'file_size_bytes', 'mime_type', 'apri_file'),
            'description': "Carica un file con 'Carica file' (consigliato) "
                           "oppure incolla un URL già pubblicato.",
        }),
        ('Versioning', {
            'fields': ('version', 'superseded_by'),
            'classes': ('collapse',),
        }),
        ('Caricato da', {
            'fields': ('uploaded_by_user', 'uploaded_by_contact'),
        }),
        ('Visibilità', {
            'fields': ('is_visible_to_sponsor',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Apri')
    def apri_file(self, obj):
        if obj and obj.pk and obj.storage_url:
            url = reverse('core:documento_apri', args=[obj.pk])
            return format_html('<a href="{}" target="_blank">📄 apri</a>', url)
        return '—'

    @admin.display(description='Tipo')
    def type_badge(self, obj):
        return format_html(
            '<span style="background:#79aec8; color:white; padding:1px 6px; '
            'border-radius:3px; font-size:0.75em;">{}</span>',
            obj.get_document_type_display()
        )

    @admin.display(description='Collegato a')
    def entity_display(self, obj):
        try:
            return f"{obj.content_type.model}: {obj.entity}"
        except Exception:
            return f"{obj.content_type.model}#{obj.object_id}"

    @admin.display(description='Dimensione')
    def file_size_display(self, obj):
        if not obj.file_size_bytes:
            return '—'
        size = obj.file_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @admin.display(description='Caricato da')
    def uploaded_by_display(self, obj):
        if obj.uploaded_by_user:
            return f"👤 {obj.uploaded_by_user.email}"
        if obj.uploaded_by_contact:
            return f"🏢 {obj.uploaded_by_contact.full_name}"
        return '—'

    @admin.display(description='Caricato il', ordering='created_at')
    def created_at_short(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M')


# =============================================================================
# EMAIL TEMPLATE (con widget multilingua)
# =============================================================================

# Punti di invio email dell'applicazione (code = nome template file/DB).
EMAIL_POINTS = [
    ('portal_invitation', 'Invito al portale'),
    ('quote_email', 'Invio preventivo'),
    ('contract_signed', 'Conferma preventivo — domanda di ammissione'),
    ('sponsor_contract_email', 'Conferma preventivo — contratto di sponsorizzazione'),
    ('payment_confirmation', 'Conferma pagamento ricevuto'),
    ('deadline_reminder', 'Reminder scadenza (T-10 / T-3 / T-0)'),
    ('deadline_overdue', 'Sollecito scadenza scaduta'),
    ('option_reminder', 'Reminder opzione spazio'),
    ('cart_recovery', 'Recupero carrello abbandonato'),
    ('operator_alert', 'Alert operatore (interno)'),
    ('password_reset', 'Reset password'),
    ('portal_message_notification', 'Notifica nuovo messaggio nel portale'),
]


class EmailTemplateForm(forms.ModelForm):
    code = forms.ChoiceField(
        choices=EMAIL_POINTS,
        label='Punto di invio',
        help_text="Quando parte questa email nel gestionale.",
    )
    subject_template = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=['it'],
        label='Oggetto',
    )
    body_template = TranslatableJSONField(
        languages=['it', 'en'],
        required_languages=['it'],
        wysiwyg=True,
        label='Corpo email',
    )

    class Meta:
        model = EmailTemplate
        fields = '__all__'

    class Media:
        js = (
            'https://cdn.jsdelivr.net/npm/tinymce@7.6.0/tinymce.min.js',
            'admin/js/email_wysiwyg.js',
        )


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    form = EmailTemplateForm

    list_display = ('punto_display', 'event_type_display', 'name', 'is_active')
    list_filter = ('event_type', 'is_active', 'code')
    search_fields = ('code', 'name', 'description')
    ordering = ('code', 'event_type')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Punto di invio', ordering='code')
    def punto_display(self, obj):
        return dict(EMAIL_POINTS).get(obj.code, obj.code)

    @admin.display(description='Tipo evento', ordering='event_type')
    def event_type_display(self, obj):
        from shared.models import EmailTemplate
        return dict(EmailTemplate.EVENT_TYPE_CHOICES).get(obj.event_type, obj.event_type) or 'Tutti'

    fieldsets = (
        (None, {
            'fields': ('code', 'event_type', 'name', 'description', 'communication_type', 'is_active'),
            'description': "Attiva il modello per farlo usare al posto dell'email predefinita. "
                           "Se non attivo (o assente), viene usato il testo standard di sistema.",
        }),
        ('Contenuto', {
            'fields': ('subject_template', 'body_template'),
            'description': "Placeholder Jinja2 supportati: {{ contact.full_name }}, "
                           "{{ event.name }}, {{ contract.contract_number }}, etc.",
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


# =============================================================================
# COMMUNICATION
# =============================================================================

@admin.register(Communication)
class CommunicationAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        from core.event_scope import scope_generic_by_event
        return scope_generic_by_event(request, super().get_queryset(request))


    list_display = (
        'subject_short', 'communication_type', 'channel',
        'recipients_short', 'status_badge', 'is_automated_icon',
        'sent_at_short', 'open_count',
    )
    list_filter = (evento_filter('contract__event'), 'status', 'communication_type', 'channel', 'is_automated')
    search_fields = ('subject', 'body_text')
    readonly_fields = (
        'created_at', 'updated_at',
        'sent_at', 'delivered_at', 'first_opened_at',
        'open_count', 'bounced_at', 'bounce_reason',
        'provider_message_id', 'provider_response',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('communication_type', 'channel', 'is_automated', 'triggered_by_user'),
        }),
        ('Riferimento entità', {
            'fields': ('content_type', 'object_id'),
        }),
        ('Destinatari', {
            'fields': ('recipients_to', 'recipients_cc', 'recipients_bcc'),
        }),
        ('Contenuto', {
            'fields': ('subject', 'body_text', 'body_html', 'attachment_document_ids'),
        }),
        ('Stato e tracking', {
            'fields': ('status', 'sent_at', 'delivered_at', 'first_opened_at',
                       'open_count', 'bounced_at', 'bounce_reason'),
        }),
        ('Provider', {
            'fields': ('provider_message_id', 'provider_response'),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Oggetto')
    def subject_short(self, obj):
        return obj.subject[:60] + '...' if obj.subject and len(obj.subject) > 60 else obj.subject

    @admin.display(description='Destinatari')
    def recipients_short(self, obj):
        recipients = obj.recipients_to or []
        if not recipients:
            return '—'
        if len(recipients) == 1:
            return recipients[0]
        return f"{recipients[0]} (+{len(recipients) - 1})"

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            CommunicationStatus.DRAFT: '#999',
            CommunicationStatus.QUEUED: '#999',
            CommunicationStatus.SENT: '#79aec8',
            CommunicationStatus.DELIVERED: '#41ad7c',
            CommunicationStatus.OPENED: '#41ad7c',
            CommunicationStatus.CLICKED: '#41ad7c',
            CommunicationStatus.BOUNCED: '#ba2121',
            CommunicationStatus.FAILED: '#ba2121',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Auto', boolean=True)
    def is_automated_icon(self, obj):
        return obj.is_automated

    @admin.display(description='Inviato il', ordering='sent_at')
    def sent_at_short(self, obj):
        if obj.sent_at:
            return obj.sent_at.strftime('%d/%m/%Y %H:%M')
        return '—'


# =============================================================================
# INVOICE EXPORT
# =============================================================================

@admin.register(InvoiceExport)
class InvoiceExportAdmin(admin.ModelAdmin):
    list_display = (
        'reference_display', 'contract_link', 'export_type',
        'amount_total_display', 'status_badge', 'external_invoice_number',
        'invoiced_at_short',
    )
    list_filter = ('status', 'export_type', 'external_system')
    search_fields = (
        'external_invoice_number', 'external_reference_id',
        'contract__contract_number', 'contract__sponsor__legal_name',
    )
    list_select_related = ('contract', 'contract__sponsor')
    autocomplete_fields = ['contract']
    readonly_fields = (
        'created_at', 'updated_at',
        'fiscal_data_snapshot', 'exported_at', 'invoiced_at', 'paid_at',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': ('contract', 'export_type', 'installment_number', 'status'),
        }),
        ('Importi', {
            'fields': ('amount_subtotal', 'amount_vat', 'amount_total'),
        }),
        ('Sistema esterno', {
            'fields': ('external_system', 'external_invoice_number',
                       'external_invoice_date', 'external_reference_id'),
        }),
        ('Date', {
            'fields': ('exported_at', 'invoiced_at', 'paid_at'),
        }),
        ('Snapshot dati fiscali', {
            'fields': ('fiscal_data_snapshot',),
            'classes': ('collapse',),
            'description': 'Dati sponsor congelati al momento dell\'export. '
                           'Servono per la fattura emessa nel sistema esterno.',
        }),
        ('Export file', {
            'fields': ('export_file_url',),
            'classes': ('collapse',),
        }),
        ('Note', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Riferimento')
    def reference_display(self, obj):
        if obj.external_invoice_number:
            return obj.external_invoice_number
        return f"PENDING #{obj.id.hex[:8]}"

    @admin.display(description='Contratto', ordering='contract__contract_number')
    def contract_link(self, obj):
        url = reverse('admin:contracts_contract_change', args=[obj.contract_id])
        return format_html('<a href="{}">{}</a>', url, obj.contract.contract_number)

    @admin.display(description='Totale', ordering='amount_total')
    def amount_total_display(self, obj):
        return format_html('<strong>€ {}</strong>', f"{obj.amount_total:,.2f}")

    @admin.display(description='Stato')
    def status_badge(self, obj):
        colors = {
            InvoiceExportStatus.PENDING_EXPORT: '#999',
            InvoiceExportStatus.EXPORTED: '#79aec8',
            InvoiceExportStatus.INVOICED: '#41ad7c',
            InvoiceExportStatus.PAID: '#41ad7c',
            InvoiceExportStatus.CANCELLED: '#ba2121',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:3px; font-size:0.85em;">{}</span>',
            color, obj.get_status_display()
        )

    @admin.display(description='Fatturato', ordering='invoiced_at')
    def invoiced_at_short(self, obj):
        if obj.invoiced_at:
            return obj.invoiced_at.strftime('%d/%m/%Y')
        return '—'


# =============================================================================
# AUDIT LOG
# =============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Sola lettura: gli audit log non si modificano mai."""
    list_display = (
        'created_at_short', 'user_display', 'action',
        'entity_short', 'has_changes_icon',
    )
    list_filter = ('action', 'entity_type', 'created_at')
    search_fields = ('action', 'entity_type', 'user__email')
    list_select_related = ('user',)
    readonly_fields = (
        'id', 'user', 'action', 'entity_type', 'entity_id',
        'changes', 'ip_address', 'user_agent', 'created_at',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Quando', ordering='created_at')
    def created_at_short(self, obj):
        return obj.created_at.strftime('%d/%m/%Y %H:%M:%S')

    @admin.display(description='Utente')
    def user_display(self, obj):
        return obj.user.email if obj.user else '—'

    @admin.display(description='Entità')
    def entity_short(self, obj):
        if obj.entity_id:
            return f"{obj.entity_type}#{str(obj.entity_id)[:8]}"
        return obj.entity_type

    @admin.display(description='Modifiche', boolean=True)
    def has_changes_icon(self, obj):
        return bool(obj.changes)



@admin.register(LetterTemplate)
class LetterTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'language', 'is_active', 'updated_at')
    list_filter = ('is_active', 'language')
    search_fields = ('name', 'body_template')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'language', 'is_active')}),
        ('Contenuto', {'fields': ('body_template',),
            'description': "Segnaposti: {{ azienda }}, {{ evento }}, {{ date_evento }}, "
                           "{{ luogo_evento }}, {{ numero }}, {{ totale }}, {{ stand }}, {{ servizi }}"}),
        ('Sistema', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
