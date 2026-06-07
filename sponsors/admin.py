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

from .models import Contact, ContactRole, MessageSender, PortalMessage, Sponsor


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


def _notifica_cliente_nuovo_messaggio(request, sponsor):
    """Avvisa via email i contatti col portale che la segreteria ha scritto.
    Mette un link diretto all'archivio messaggi del portale. Non blocca mai."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.urls import reverse
    try:
        recipients = list(
            sponsor.contacts.filter(has_portal_access=True)
            .exclude(email='').values_list('email', flat=True))
        if not recipients:
            return
        try:
            url = request.build_absolute_uri(reverse('portal:messages'))
        except Exception:
            url = (getattr(settings, 'PORTAL_URL', '') or '').rstrip('/')
        subject = "La segreteria ha risposto al tuo messaggio"
        body = (
            "Ciao,\n\nla segreteria organizzativa ha pubblicato un messaggio per te "
            "nel portale.\n\n"
            f"Vai a leggerlo qui: {url}\n\n"
            "A presto."
        )
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients,
                  fail_silently=True)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Notifica messaggio al cliente non inviata")


def _badge(color, text, bold=False):
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 8px;border-radius:3px;'
        'font-size:.85em;{}">{}</span>',
        color, 'font-weight:700;' if bold else '', text)


def _stato_messaggio_badge(msg):
    if msg.sender == MessageSender.SPONSOR:
        # risposta del cliente: "letto" = letto dall'operatore
        if msg.is_read:
            return _badge('#41ad7c', 'RISPOSTA (letta)')
        return _badge('#c0392b', '↩ RISPOSTA CLIENTE — DA LEGGERE', bold=True)
    # messaggio dell'operatore: "letto" = letto dal cliente
    if msg.is_read:
        return _badge('#41ad7c', 'letto dal cliente')
    return _badge('#e6a23c', 'da leggere (cliente)', bold=True)


class PortalMessageInline(admin.TabularInline):
    """Conversazione col portale di questo sponsor (messaggi + risposte cliente)."""
    model = PortalMessage
    fk_name = 'sponsor'
    extra = 0
    fields = ('mittente', 'body', 'parent', 'is_active', 'stato', 'letto_il', 'letto_da')
    readonly_fields = ('mittente', 'stato', 'letto_il', 'letto_da')
    verbose_name = 'Messaggio'
    verbose_name_plural = 'Conversazione col portale (scrivi in basso; per rispondere a un thread scegli "In risposta a")'
    ordering = ('created_at',)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        ff = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == 'body' and ff is not None:
            ff.widget.attrs.update({
                'rows': 1,
                'style': 'width:26em; height:2.4em; min-height:2.4em; resize:both;',
            })
        return ff

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'parent':
            sponsor_id = None
            try:
                sponsor_id = request.resolver_match.kwargs.get('object_id')
            except Exception:
                sponsor_id = None
            if sponsor_id:
                kwargs['queryset'] = PortalMessage.objects.filter(
                    sponsor_id=sponsor_id, parent__isnull=True).order_by('-created_at')
            else:
                kwargs['queryset'] = PortalMessage.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Da')
    def mittente(self, obj):
        if not obj or not obj.pk:
            return '(operatore)'
        if obj.sender == MessageSender.SPONSOR:
            return format_html('<strong style="color:#1f4e79;">Cliente</strong>')
        return 'Operatore'

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
    readonly_fields = ('created_at', 'updated_at', 'contracts_summary',
                       'logo_preview', 'conversazione_display')
    ordering = (Lower('legal_name'),)
    inlines = [ContactInline]
    actions = ['action_generate_client_summary', 'action_compose_email']

    def save_formset(self, request, form, formset, change):
        from django.utils import timezone
        instances = formset.save(commit=False)
        roots_risposti = set()
        operatore_ha_scritto = False
        for obj in instances:
            if isinstance(obj, PortalMessage):
                _nuovo = obj._state.adding
                if obj.created_by_id is None:
                    obj.created_by = request.user
                if not obj.sender:
                    obj.sender = MessageSender.OPERATOR
                obj.save()
                if obj.sender == MessageSender.OPERATOR and _nuovo:
                    operatore_ha_scritto = True
                # se l'operatore risponde in un thread, segnerà lette le risposte cliente
                if obj.sender == MessageSender.OPERATOR and obj.parent_id:
                    roots_risposti.add(obj.parent_id)
            else:
                obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()
        if roots_risposti:
            PortalMessage.objects.filter(
                Q(pk__in=roots_risposti) | Q(parent_id__in=roots_risposti),
                sender=MessageSender.SPONSOR, read_at__isnull=True,
            ).update(read_at=timezone.now())
        # un'unica email al cliente se la segreteria ha scritto nuovi messaggi
        if operatore_ha_scritto:
            _notifica_cliente_nuovo_messaggio(request, form.instance)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'messaggio/<uuid:message_id>/letto/',
                self.admin_site.admin_view(self.mark_message_read_view),
                name='sponsors_messaggio_letto',
            ),
            path(
                '<path:object_id>/conversazione/',
                self.admin_site.admin_view(self.conversazione_view),
                name='sponsors_sponsor_conversazione',
            ),
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
        ('Conversazione col portale', {
            'fields': ('conversazione_display',),
            'description': "Lo scambio di messaggi col cliente. Per scrivere o "
                           "rispondere usa il pulsante «Apri / continua la "
                           "conversazione».",
        }),
        ('Riepilogo contratti', {
            'fields': ('contracts_summary',),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Conversazione')
    def conversazione_display(self, obj):
        from django.utils.safestring import mark_safe
        if not obj or not obj.pk:
            return "—"
        conv_url = reverse('admin:sponsors_sponsor_conversazione', args=[obj.pk])
        tot = obj.portal_messages.filter(is_active=True).count()
        da_leggere = obj.portal_messages.filter(
            is_active=True, sender=MessageSender.SPONSOR, read_at__isnull=True).count()
        btn = (f'<a href="{conv_url}" class="button" '
               f'style="display:inline-block;background:#2e7d32;color:#fff;'
               f'padding:8px 16px;border-radius:8px;font-weight:600;">'
               f'💬 Apri conversazione col portale</a>')
        if tot == 0:
            info = '<span style="color:#888;">Nessun messaggio.</span>'
        else:
            info = f'<span style="color:#555;">{tot} messaggio/i</span>'
            if da_leggere:
                info += (f' · <span style="color:#c0392b;font-weight:700;">'
                         f'{da_leggere} risposta/e da leggere</span>')
        return mark_safe(f'{btn} &nbsp; {info}')

    def conversazione_view(self, request, object_id):
        """Pagina chat: leggi il thread e rispondi (o apri un nuovo messaggio).
        Aprendo la pagina, le risposte del cliente vengono segnate come lette."""
        from django.shortcuts import get_object_or_404, redirect, render
        from django.utils import timezone

        sponsor = get_object_or_404(Sponsor, pk=object_id)

        if request.method == 'POST':
            body = (request.POST.get('body') or '').strip()
            reply_to = (request.POST.get('reply_to') or '').strip()
            if not body:
                self.message_user(request, "Scrivi un testo prima di inviare.",
                                  level=messages.WARNING)
                return redirect(request.path)
            parent = None
            if reply_to:
                p = PortalMessage.objects.filter(pk=reply_to, sponsor=sponsor).first()
                parent = (p.parent or p) if p else None
            PortalMessage.objects.create(
                sponsor=sponsor, sender=MessageSender.OPERATOR, parent=parent,
                body=body, is_active=True, created_by=request.user)
            _notifica_cliente_nuovo_messaggio(request, sponsor)
            self.message_user(request, "Messaggio inviato al cliente.",
                              level=messages.SUCCESS)
            return redirect(request.path)

        # GET: l'operatore sta leggendo -> segna lette le risposte del cliente
        PortalMessage.objects.filter(
            sponsor=sponsor, sender=MessageSender.SPONSOR,
            read_at__isnull=True, is_active=True).update(read_at=timezone.now())

        msgs = list(sponsor.portal_messages.filter(is_active=True)
                    .select_related('parent', 'read_by').order_by('created_at'))
        figli = {}
        for m in msgs:
            if m.parent_id:
                figli.setdefault(m.parent_id, []).append(m)
        threads = []
        for root in [m for m in msgs if m.parent_id is None]:
            threads.append({
                'root': root,
                'messages': [root] + sorted(figli.get(root.id, []),
                                            key=lambda x: x.created_at),
            })

        context = {
            **self.admin_site.each_context(request),
            'title': f'Conversazione · {sponsor}',
            'sponsor': sponsor,
            'threads': threads,
            'opts': self.model._meta,
        }
        return render(request, 'admin/sponsors/conversazione.html', context)

    def mark_message_read_view(self, request, message_id):
        from django.shortcuts import get_object_or_404, redirect
        msg = get_object_or_404(PortalMessage, id=message_id)
        msg.mark_read()
        self.message_user(request, "Messaggio segnato come letto.", level=messages.SUCCESS)
        # torna da dove si arrivava (lista o scheda sponsor)
        ref = request.META.get('HTTP_REFERER')
        if ref:
            return redirect(ref)
        return redirect(reverse('admin:sponsors_sponsor_change', args=[msg.sponsor_id]))

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
    readonly_fields = ('created_at', 'updated_at',
                       'privacy_accepted_at', 'privacy_policy_version',
                       'marketing_consent_at')
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
        ('Privacy e consensi', {
            'fields': ('privacy_accepted_at', 'privacy_policy_version',
                       'marketing_consent', 'marketing_consent_at'),
            'description': "Presa visione informativa e consenso marketing "
                           "(registrati automaticamente dal portale).",
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


class _MittenteFilter(admin.SimpleListFilter):
    title = 'Mittente'
    parameter_name = 'mitt'

    def lookups(self, request, model_admin):
        return (('operator', 'Operatore'), ('sponsor', 'Cliente (risposte)'))

    def queryset(self, request, queryset):
        if self.value() in ('operator', 'sponsor'):
            return queryset.filter(sender=self.value())
        return queryset


@admin.register(PortalMessage)
class PortalMessageAdmin(admin.ModelAdmin):
    """Archivio conversazioni col portale, con stato letto / da leggere."""
    list_display = ('sponsor', 'mittente', 'estratto', 'stato', 'azioni',
                    'event', 'is_active', 'created_at', 'created_by')
    list_filter = (('sponsor', admin.RelatedOnlyFieldListFilter),
                   _MittenteFilter, _LettoFilter, 'is_active', 'event')
    search_fields = ('sponsor__legal_name', 'sponsor__display_name', 'body')
    list_select_related = ('sponsor', 'event', 'read_by', 'created_by', 'parent')
    autocomplete_fields = ['sponsor', 'event', 'parent']
    readonly_fields = ('read_at', 'read_by', 'created_by', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    actions = ['action_segna_letto']
    fieldsets = (
        (None, {'fields': ('sponsor', 'event', 'parent', 'body', 'is_active')}),
        ('Stato lettura', {'fields': ('read_at', 'read_by')}),
        ('Sistema', {'fields': ('created_by', 'created_at', 'updated_at'),
                     'classes': ('collapse',)}),
    )

    def changelist_view(self, request, extra_context=None):
        """Invece del classico elenco riga-per-riga, mostra una INBOX di
        conversazioni (una per sponsor): clic -> chat del singolo sponsor."""
        from django.shortcuts import render
        from sponsors.models import Sponsor

        q = (request.GET.get('q') or '').strip()
        sponsors = Sponsor.objects.filter(portal_messages__is_active=True).distinct()
        if q:
            sponsors = sponsors.filter(
                Q(legal_name__icontains=q) | Q(display_name__icontains=q))

        conversazioni = []
        for sp in sponsors:
            msgs = sp.portal_messages.filter(is_active=True)
            last = msgs.order_by('-created_at').first()
            unread = msgs.filter(
                sender=MessageSender.SPONSOR, read_at__isnull=True).count()
            conversazioni.append({
                'sponsor': sp,
                'last': last,
                'unread': unread,
                'url': reverse('admin:sponsors_sponsor_conversazione', args=[sp.pk]),
            })
        conversazioni.sort(key=lambda c: (
            0 if c['unread'] else 1,
            -(c['last'].created_at.timestamp() if c['last'] else 0),
        ))

        context = {
            **self.admin_site.each_context(request),
            'title': 'Messaggi portale',
            'conversazioni': conversazioni,
            'opts': self.model._meta,
            'q': q,
        }
        return render(request, 'admin/sponsors/conversazioni_inbox.html', context)

    @admin.display(description='Da')
    def mittente(self, obj):
        if obj.sender == MessageSender.SPONSOR:
            return format_html('<strong style="color:#1f4e79;">Cliente</strong>')
        return 'Operatore'

    @admin.display(description='Messaggio')
    def estratto(self, obj):
        t = (obj.body or '').strip().replace('\n', ' ')
        return (t[:60] + '…') if len(t) > 60 else t

    @admin.display(description='Stato')
    def stato(self, obj):
        badge = _stato_messaggio_badge(obj)
        if obj.sender == MessageSender.SPONSOR and not obj.is_read:
            url = reverse('admin:sponsors_messaggio_letto', args=[obj.id])
            return format_html('{} &nbsp;<a href="{}">✓ segna letto</a>', badge, url)
        return badge

    @admin.display(description='Azioni')
    def azioni(self, obj):
        url = reverse('admin:sponsors_sponsor_conversazione', args=[obj.sponsor_id])
        return format_html('<a href="{}">💬 apri / rispondi →</a>', url)

    @admin.action(description='Segna come letto')
    def action_segna_letto(self, request, queryset):
        from django.utils import timezone
        n = queryset.filter(read_at__isnull=True).update(read_at=timezone.now())
        self.message_user(request, f"{n} messaggio/i segnato/i come letto/i.")

    def save_model(self, request, obj, form, change):
        _nuovo = obj._state.adding
        if obj.created_by_id is None:
            obj.created_by = request.user
        if not obj.sender:
            obj.sender = MessageSender.OPERATOR
        super().save_model(request, obj, form, change)
        if _nuovo and obj.sender == MessageSender.OPERATOR:
            _notifica_cliente_nuovo_messaggio(request, obj.sponsor)
