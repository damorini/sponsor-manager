"""
Admin per Sponsor e Contact.

I Contact sono editati come inline dentro il form dello Sponsor: vedi tutti
i contatti di un'azienda nella stessa schermata.
"""
from django import forms
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect
from django.db.models import Count, Q, Func, CharField
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.html import format_html

from .models import Contact, ContactRole, PortalMessage, Sponsor


class _Cognome(Func):
    """Ultima parola del 'Nome completo' (= cognome), per l'ordinamento."""
    function = 'regexp_replace'
    template = "regexp_replace(trim(%(expressions)s), '^.* ', '')"
    output_field = CharField()


class ContactRolesForm(forms.ModelForm):
    """Ruoli funzionali come caselle da spuntare (invece del campo testo)."""
    roles = forms.MultipleChoiceField(
        choices=ContactRole.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ruoli funzionali",
        help_text="Determina chi riceve quali comunicazioni",
    )

    class Meta:
        model = Contact
        fields = '__all__'


class ContactInline(admin.TabularInline):
    """Contatti editabili dentro la pagina Sponsor."""
    form = ContactRolesForm
    model = Contact
    extra = 1
    fields = (
        'full_name', 'email', 'phone', 'job_title', 'roles',
        'is_primary', 'preferred_language', 'has_portal_access',
    )
    show_change_link = True

    class Media:
        css = {'all': ('admin/css/sponsor_contact_inline.css',)}


def _stato_messaggio_badge(msg):
    if msg.is_read:
        return format_html(
            '<span style="background:#41ad7c;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:.85em;">LETTO</span>')
    return format_html(
        '<span style="background:#e6a23c;color:#fff;padding:2px 8px;'
        'border-radius:3px;font-size:.85em;font-weight:700;">DA LEGGERE</span>')


class PortalMessageInline(admin.TabularInline):
    """Messaggi al portale di questo sponsor, con stato letto/da leggere."""
    model = PortalMessage
    extra = 0
    fields = ('body', 'event', 'is_active', 'stato', 'letto_il', 'letto_da')
    readonly_fields = ('stato', 'letto_il', 'letto_da')
    verbose_name = 'Messaggio portale'
    verbose_name_plural = 'Messaggi al portale (archivio)'
    ordering = ('-created_at',)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        ff = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'body' and ff is not None:
            # Textarea a 1 riga (espandibile a mano), non occupa tutto lo spazio.
            ff.widget.attrs.update({
                'rows': 1,
                'style': 'width:26em; height:2.4em; min-height:2.4em; resize:both;',
            })
        return ff

    @admin.display(description='Stato')
    def stato(self, obj):
        if not obj.pk:
            return '—'
        return _stato_messaggio_badge(obj)

    @admin.display(description='Letto il')
    def letto_il(self, obj):
        if not obj.pk or not obj.read_at:
            return '—'
        from django.utils import timezone
        return timezone.localtime(obj.read_at).strftime('%d/%m/%Y %H:%M')

    @admin.display(description='Letto da')
    def letto_da(self, obj):
        if not obj.pk or not obj.read_by_id:
            return '—'
        return obj.read_by.full_name


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = (
        'impersona_link',
        'legal_name', 'display_name_or_dash', 'vat_number',
        'address_city', 'industry',
        'contracts_count', 'has_active_contracts',
    )
    list_display_links = ('legal_name',)
    list_filter = (
        'industry', 'address_country',
    )
    search_fields = (
        'legal_name', 'display_name', 'vat_number', 'tax_code',
        'address_city', 'pec_email',
    )
    readonly_fields = ('created_at', 'updated_at', 'contracts_summary', 'logo_preview')
    ordering = (Lower('legal_name'),)
    inlines = [ContactInline, PortalMessageInline]
    actions = ['action_generate_client_summary', 'action_compose_email']

    def save_formset(self, request, form, formset, change):
        # Imposta 'inviato da' sui nuovi messaggi portale creati dall'inline.
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, PortalMessage) and obj.created_by_id is None:
                obj.created_by = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<path:object_id>/genera-scheda/',
                self.admin_site.admin_view(self.generate_summary_view),
                name='sponsors_sponsor_generate_summary',
            ),
            path(
                '<path:object_id>/invia-email/',
                self.admin_site.admin_view(self.compose_email_view),
                name='sponsors_sponsor_compose_email',
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

    # ---- Invio email singola a uno sponsor (Fase C) ----
    @admin.action(description='INVIA EMAIL a questo sponsor')
    def action_compose_email(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Seleziona UN solo sponsor.",
                              level=messages.WARNING)
            return
        sponsor = queryset.first()
        return HttpResponseRedirect(
            reverse('admin:sponsors_sponsor_compose_email', args=[sponsor.pk])
        )

    def compose_email_view(self, request, object_id):
        sponsor = get_object_or_404(Sponsor, pk=object_id)
        contacts = list(sponsor.contacts.all())
        events = self._events_of_sponsor(sponsor)

        if not contacts:
            self.message_user(request,
                              f"{sponsor.legal_name} non ha contatti con email.",
                              level=messages.WARNING)
            return HttpResponseRedirect('../../')

        if request.method == 'POST':
            to_emails = request.POST.getlist('to_emails')
            subject = (request.POST.get('subject') or '').strip()
            body = request.POST.get('body') or ''
            language = (request.POST.get('language') or 'it').strip()
            ev_id = request.POST.get('event_id') or ''

            # solo contatti dello sponsor (niente indirizzi arbitrari)
            chosen = [c for c in contacts if c.email in to_emails]
            contact = (next((c for c in chosen if getattr(c, 'is_primary', False)), None)
                       or (chosen[0] if chosen else None))
            event = None
            if ev_id:
                event = next((e['obj'] for e in events if str(e['id']) == str(ev_id)), None)

            errors = []
            if not chosen:
                errors.append("Scegli almeno un destinatario tra i contatti dello sponsor.")
            if not subject:
                errors.append("L'oggetto e' obbligatorio.")
            if not body.strip():
                errors.append("Il corpo dell'email e' obbligatorio.")

            if not errors:
                from contracts.services.email_sender import send_email
                ctx = {'sponsor': sponsor, 'contact': contact}
                if event is not None:
                    ctx['event'] = event
                    ctx['event_name'] = (event.get_name(language)
                                         if hasattr(event, 'get_name') else str(event))
                try:
                    send_email(
                        template_name='manual',
                        context=ctx,
                        to=[c.email for c in chosen],
                        subject=subject,
                        language=language or 'it',
                        related_to=sponsor,
                        communication_type='manual',
                        triggered_by_user=request.user,
                        custom_body_html=body,
                    )
                    dest = ", ".join(c.email for c in chosen)
                    self.message_user(
                        request,
                        f"Email inviata a {len(chosen)} destinatario/i: {dest}.",
                        level=messages.SUCCESS,
                    )
                    return HttpResponseRedirect('../../')
                except Exception as e:
                    errors.append(f"Invio non riuscito: {e}")

            for m in errors:
                self.message_user(request, m, level=messages.ERROR)
            form_data = {'to_emails': to_emails, 'subject': subject,
                         'body': body, 'language': language, 'event_id': ev_id}
        else:
            primary = next((c for c in contacts if getattr(c, 'is_primary', False)), None)
            default_to = [primary.email] if primary else ([contacts[0].email] if contacts else [])
            form_data = {'to_emails': default_to, 'subject': '', 'body': '',
                         'language': 'it', 'event_id': ''}

        context = {
            **self.admin_site.each_context(request),
            'title': 'Invia email',
            'sponsor': sponsor,
            'contacts': contacts,
            'events': events,
            'form_data': form_data,
            'opts': self.model._meta,
        }
        return render(request, 'admin/compose_email.html', context)


    fieldsets = (
        ('Anagrafica', {
            'fields': ('legal_name', 'display_name', 'industry', 'website', 'logo_url', 'logo_file', 'logo_preview'),
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
    @admin.display(description="Entra")
    def impersona_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        has_portal = obj.contacts.filter(
            has_portal_access=True, portal_user__isnull=False).exists()
        if not has_portal:
            return format_html(
                '<span title="Nessun contatto con accesso al portale" '
                'style="font-size:18px;opacity:0.25;">&#128065;&#65039;</span>')
        try:
            url = reverse('portal:impersonate_start', args=[obj.pk])
        except Exception:
            return ""
        return format_html(
            '<a href="{}" title="Entra come questo cliente" '
            'style="font-size:18px;text-decoration:none;">&#128065;&#65039;</a>', url)

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

    @admin.display(description='Anteprima logo')
    def logo_preview(self, obj):
        from django.utils.html import format_html
        url = None
        if getattr(obj, 'logo_file', None):
            try:
                url = obj.logo_file.url
            except Exception:
                url = None
        if not url and getattr(obj, 'logo_url', ''):
            url = obj.logo_url
        if url:
            return format_html(
                '<img src="{}" style="max-height:80px; max-width:200px; '
                'object-fit:contain; border:1px solid #ddd; border-radius:4px;">', url)
        return "(nessun logo)"

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
    form = ContactRolesForm

    class Media:
        css = {'all': ('admin/css/contact_changelist.css',)}

    list_display = (
        'full_name', 'sponsor_link', 'email', 'cellulare', 'job_title',
        'roles_display', 'col_principale', 'col_lingua', 'col_portale',
    )
    list_filter = (
        'is_primary', 'has_portal_access', 'preferred_language',
        'marketing_consent',
    )
    search_fields = ('full_name', 'email', 'phone', 'sponsor__legal_name')

    def get_search_results(self, request, queryset, search_term):
        queryset, may_dup = super().get_search_results(request, queryset, search_term)
        if "/autocomplete/" in request.path:
            _sp = request.GET.get("sponsor")
            if _sp:
                queryset = queryset.filter(sponsor_id=_sp)
        return queryset, may_dup
    list_select_related = ('sponsor',)
    autocomplete_fields = ['sponsor', 'portal_user']
    readonly_fields = ('created_at', 'updated_at')
    actions = ['action_invita_al_portale']
    def get_ordering(self, request):
        # Espressione autosufficiente: ordina per "cognome" ricavato da full_name,
        # senza annotazioni. Cosi' funziona anche quando un altro admin (es. il
        # Contratto) costruisce la tendina dei Contatti via get_field_queryset.
        return (Lower(_Cognome('full_name')),)

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

    @admin.display(description='Cellulare', ordering='phone')
    def cellulare(self, obj):
        return obj.phone or '—'

    @admin.display(description='Princip.', boolean=True, ordering='is_primary')
    def col_principale(self, obj):
        return obj.is_primary

    @admin.display(description='Lingua', ordering='preferred_language')
    def col_lingua(self, obj):
        return obj.preferred_language

    @admin.display(description='Portale', boolean=True, ordering='has_portal_access')
    def col_portale(self, obj):
        return obj.has_portal_access

    @admin.display(description='Sponsor', ordering='sponsor__legal_name')
    def sponsor_link(self, obj):
        url = reverse('admin:sponsors_sponsor_change', args=[obj.sponsor_id])
        return format_html('<a href="{}">{}</a>', url, obj.sponsor.legal_name)

    @admin.action(description='Invita al portale (crea utente + password)')
    def action_invita_al_portale(self, request, queryset):
        from portal.services.invitation import invite_contact_to_portal
        ok_creati, ok_reset, errori = 0, 0, []
        righe = []
        for contact in queryset:
            try:
                user, pwd, created = invite_contact_to_portal(contact, send_email=False)
                righe.append(f"{contact.full_name} ({user.email}) - password: {pwd}"
                             + ("" if created else " (rigenerata)"))
                if created:
                    ok_creati += 1
                else:
                    ok_reset += 1
            except Exception as e:
                errori.append(f"{contact.full_name}: {e}")

        if ok_creati or ok_reset:
            msg = "Inviti completati. " + " | ".join(righe)
            self.message_user(request, msg, level='SUCCESS')
        if errori:
            self.message_user(request, "Errori: " + " | ".join(errori), level='ERROR')

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


class _LettoFilter(admin.SimpleListFilter):
    title = 'Stato lettura'
    parameter_name = 'letto'

    def lookups(self, request, model_admin):
        return (('si', 'Letto'), ('no', 'Da leggere'))

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.filter(read_at__isnull=False)
        if self.value() == 'no':
            return queryset.filter(read_at__isnull=True)
        return queryset


@admin.register(PortalMessage)
class PortalMessageAdmin(admin.ModelAdmin):
    """Archivio messaggi al portale, con stato letto / da leggere."""
    list_display = ('sponsor', 'estratto', 'stato', 'event', 'is_active',
                    'created_at', 'read_at', 'created_by')
    list_filter = (_LettoFilter, 'is_active', 'event')
    search_fields = ('sponsor__legal_name', 'sponsor__display_name', 'body')
    list_select_related = ('sponsor', 'event', 'read_by', 'created_by')
    autocomplete_fields = ['sponsor', 'event']
    readonly_fields = ('read_at', 'read_by', 'created_by', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('sponsor', 'event', 'body', 'is_active')}),
        ('Stato lettura', {'fields': ('read_at', 'read_by')}),
        ('Sistema', {'fields': ('created_by', 'created_at', 'updated_at'),
                     'classes': ('collapse',)}),
    )

    @admin.display(description='Messaggio')
    def estratto(self, obj):
        t = (obj.body or '').strip().replace('\n', ' ')
        return (t[:60] + '…') if len(t) > 60 else t

    @admin.display(description='Stato')
    def stato(self, obj):
        return _stato_messaggio_badge(obj)

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
