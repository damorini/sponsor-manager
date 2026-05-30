"""
Admin per app shared: Document, Communication, EmailTemplate,
InvoiceExport, AuditLog.

EmailTemplate ha widget multilingua per subject e body.
"""
from django import forms
from django.contrib import admin
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

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'type_badge', 'entity_display',
        'file_name', 'file_size_display', 'uploaded_by_display',
        'is_visible_to_sponsor', 'created_at_short',
    )
    list_filter = ('document_type', 'storage_provider', 'is_visible_to_sponsor')
    search_fields = ('title', 'file_name', 'description')
    list_select_related = ('content_type', 'uploaded_by_user', 'uploaded_by_contact')
    readonly_fields = (
        'created_at', 'updated_at',
        'file_size_bytes', 'mime_type',
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
            'fields': ('storage_url', 'storage_provider', 'file_name',
                       'file_size_bytes', 'mime_type'),
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

class EmailTemplateForm(forms.ModelForm):
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

    list_display = ('code', 'name', 'communication_type', 'is_active')
    list_filter = ('is_active', 'communication_type')
    search_fields = ('code', 'name', 'description')
    ordering = ('code',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'description', 'communication_type', 'is_active'),
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
    list_display = (
        'subject_short', 'communication_type', 'channel',
        'recipients_short', 'status_badge', 'is_automated_icon',
        'sent_at_short', 'open_count',
    )
    list_filter = ('status', 'communication_type', 'channel', 'is_automated')
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
