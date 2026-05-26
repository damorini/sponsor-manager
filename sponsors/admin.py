"""
Admin per Sponsor e Contact.

I Contact sono editati come inline dentro il form dello Sponsor: vedi tutti
i contatti di un'azienda nella stessa schermata.
"""
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

from .models import Contact, ContactRole, Sponsor


class ContactInline(admin.TabularInline):
    """Contatti editabili dentro la pagina Sponsor."""
    model = Contact
    extra = 1
    fields = (
        'full_name', 'email', 'phone', 'job_title', 'roles',
        'is_primary', 'preferred_language', 'has_portal_access',
    )
    show_change_link = True


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = (
        'legal_name', 'display_name_or_dash', 'vat_number',
        'address_city', 'industry',
        'contracts_count', 'has_active_contracts',
    )
    list_filter = (
        'industry', 'address_country',
    )
    search_fields = (
        'legal_name', 'display_name', 'vat_number', 'tax_code',
        'address_city', 'pec_email',
    )
    readonly_fields = ('created_at', 'updated_at', 'contracts_summary')
    ordering = ('legal_name',)
    inlines = [ContactInline]
    actions = ['action_generate_client_summary']

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/genera-scheda/',
                self.admin_site.admin_view(self.generate_summary_view),
                name='sponsors_sponsor_generate_summary',
            ),
        ]
        return custom + urls

    def _events_of_sponsor(self, sponsor):
        """Eventi distinti dai contratti non annullati dello sponsor."""
        from contracts.models import ContractStatus
        seen = {}
        qs = (sponsor.contracts
              .exclude(status=ContractStatus.CANCELLED)
              .select_related('event'))
        for c in qs:
            ev = c.event
            if ev.id not in seen:
                lang = getattr(c, 'language', None) or 'it'
                label = ev.get_name(lang) if hasattr(ev, 'get_name') else str(ev)
                seen[ev.id] = {'id': ev.id, 'obj': ev, 'label': label}
        return list(seen.values())

    def _genera_e_messaggio(self, request, sponsor, event):
        from contracts.services.pdf_generator import generate_client_summary_pdf
        try:
            document = generate_client_summary_pdf(sponsor, event)
        except ValueError as e:
            self.message_user(request, str(e), level=messages.ERROR)
            return
        except Exception as e:
            self.message_user(request, f"Errore nella generazione della scheda: {e}",
                              level=messages.ERROR)
            return
        from django.utils.html import format_html
        self.message_user(
            request,
            format_html('Scheda cliente generata: <a href="{}" target="_blank">apri il PDF</a>',
                        document.storage_url),
            level=messages.SUCCESS,
        )

    @admin.action(description='Genera SCHEDA CLIENTE (scegli evento)')
    def action_generate_client_summary(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Seleziona UN solo sponsor.",
                              level=messages.WARNING)
            return
        sponsor = queryset.first()
        return HttpResponseRedirect(
            reverse('admin:sponsors_sponsor_generate_summary', args=[sponsor.pk])
        )

    def generate_summary_view(self, request, object_id):
        sponsor = get_object_or_404(Sponsor, pk=object_id)
        events = self._events_of_sponsor(sponsor)

        if not events:
            self.message_user(request,
                              f"{sponsor.legal_name} non ha contratti: scheda non generabile.",
                              level=messages.WARNING)
            return HttpResponseRedirect('../../')

        # 1 solo evento -> genera diretto
        if len(events) == 1 and request.method == 'GET':
            self._genera_e_messaggio(request, sponsor, events[0]['obj'])
            return HttpResponseRedirect('../../')

        # POST: evento scelto
        if request.method == 'POST':
            ev_id = request.POST.get('event_id')
            chosen = next((e for e in events if str(e['id']) == str(ev_id)), None)
            if not chosen:
                self.message_user(request, "Evento non valido.", level=messages.ERROR)
                return HttpResponseRedirect(request.path)
            self._genera_e_messaggio(request, sponsor, chosen['obj'])
            return HttpResponseRedirect('../../')

        # GET con piu' eventi -> pagina di scelta
        context = {
            **self.admin_site.each_context(request),
            'title': 'Genera scheda cliente',
            'sponsor': sponsor,
            'events': events,
            'opts': self.model._meta,
        }
        return render(request, 'admin/client_summary_event_choice.html', context)


    fieldsets = (
        ('Anagrafica', {
            'fields': ('legal_name', 'display_name', 'industry', 'website', 'logo_url'),
        }),
        ('Dati fiscali', {
            'fields': ('vat_number', 'tax_code', 'sdi_code', 'pec_email'),
        }),
        ('Sede legale', {
            'fields': (
                'address_street',
                ('address_zip', 'address_city', 'address_province'),
                'address_country',
            ),
        }),
        ('Note', {
            'fields': ('notes',),
            'classes': ('collapse',),
        }),
        ('Riepilogo contratti', {
            'fields': ('contracts_summary',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _contracts_count=Count(
                'contracts',
                filter=Q(contracts__deleted_at__isnull=True),
            ),
            _active_contracts=Count(
                'contracts',
                filter=Q(contracts__deleted_at__isnull=True) &
                       Q(contracts__status__in=['signed', 'active']),
            ),
        )

    @admin.display(description='Nome breve')
    def display_name_or_dash(self, obj):
        return obj.display_name or '—'

    @admin.display(description='Contratti', ordering='_contracts_count')
    def contracts_count(self, obj):
        return getattr(obj, '_contracts_count', 0)

    @admin.display(description='Attivi', boolean=False, ordering='_active_contracts')
    def has_active_contracts(self, obj):
        active = getattr(obj, '_active_contracts', 0)
        if active > 0:
            return format_html(
                '<span style="color:#41ad7c; font-weight:bold;">✓ {}</span>',
                active
            )
        return '—'

    @admin.display(description='Riepilogo')
    def contracts_summary(self, obj):
        if not obj.pk:
            return '—'

        contracts_url = reverse('admin:contracts_contract_changelist') + f'?sponsor__id__exact={obj.pk}'

        return format_html(
            '<a href="{}" class="button">Vedi tutti i contratti di questo sponsor</a>',
            contracts_url
        )


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    """Admin separato per cercare contatti tra tutti gli sponsor."""
    list_display = (
        'full_name', 'sponsor_link', 'email', 'job_title',
        'roles_display', 'is_primary', 'preferred_language', 'has_portal_access',
    )
    list_filter = (
        'is_primary', 'has_portal_access', 'preferred_language',
        'marketing_consent',
    )
    search_fields = ('full_name', 'email', 'phone', 'sponsor__legal_name')
    list_select_related = ('sponsor',)
    autocomplete_fields = ['sponsor', 'portal_user']
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Persona', {
            'fields': ('sponsor', 'full_name', 'email', 'phone', 'job_title'),
        }),
        ('Funzioni', {
            'fields': ('roles', 'is_primary', 'preferred_language'),
        }),
        ('Firmatario contratti', {
            'fields': (
                'is_signer', 'signer_tax_code',
                ('birth_date', 'birth_place', 'birth_province'),
                ('residence_street', 'residence_street_number'),
                ('residence_city', 'residence_zip', 'residence_province'),
                ('id_document_type', 'id_document_number'),
            ),
            'classes': ('collapse',),
            'description': "Compila solo se il contatto è il legale rappresentante "
                          "che firma i contratti per conto dello sponsor.",
        }),
        ('Portale sponsor', {
            'fields': ('has_portal_access', 'portal_user'),
            'description': 'Se has_portal_access è True, deve essere collegato un User.',
        }),
        ('Consenso', {
            'fields': ('marketing_consent',),
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

    @admin.display(description='Sponsor', ordering='sponsor__legal_name')
    def sponsor_link(self, obj):
        url = reverse('admin:sponsors_sponsor_change', args=[obj.sponsor_id])
        return format_html('<a href="{}">{}</a>', url, obj.sponsor.legal_name)

    @admin.display(description='Ruoli')
    def roles_display(self, obj):
        if not obj.roles:
            return '—'
        labels = {choice.value: choice.label for choice in ContactRole}
        badges = ''.join([
            format_html(
                '<span style="background:#79aec8; color:white; padding:1px 6px; '
                'border-radius:3px; font-size:0.75em; margin-right:2px;">{}</span>',
                labels.get(r, r)
            )
            for r in obj.roles
        ])
        return format_html(badges)
