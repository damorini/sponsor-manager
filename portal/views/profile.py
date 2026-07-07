"""Vista profilo: lo sponsor modifica la propria anagrafica."""
import logging
from io import BytesIO

from django.contrib import messages
from django.core.files.base import ContentFile
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from portal.views.dashboard import sponsor_required


def _comprimi_logo(uploaded_file, max_side=400):
    """Ridimensiona (max_side px lato lungo) e comprime un'immagine caricata.
    Ritorna un ContentFile PNG ottimizzato. Solleva ValueError se non e' immagine."""
    from PIL import Image
    try:
        img = Image.open(uploaded_file)
        img.load()
    except Exception:
        raise ValueError("Il file caricato non e' un'immagine valida.")
    # converti in RGBA per preservare trasparenza, poi salva PNG ottimizzato
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGBA')
    w, h = img.size
    if max(w, h) > max_side:
        if w >= h:
            nw, nh = max_side, int(h * max_side / w)
        else:
            nw, nh = int(w * max_side / h), max_side
        img = img.resize((nw, nh), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return ContentFile(buf.read())

from django.utils.translation import gettext_lazy as _
logger = logging.getLogger(__name__)

# Ruoli funzionali disponibili (value, label)
CONTACT_ROLE_CHOICES = [
    ('signer', _('Firmatario')),
    ('marketing', _('Marketing')),
    ('finance', _('Amministrazione')),
    ('operational', _('Operativo')),
    ('cc', _('CC')),
    ('educational', _('Educational manager')),
]

# Campi modificabili (nome_campo_modello -> etichetta)
SPONSOR_FIELDS = [
    ('legal_name', _('Ragione sociale')),
    ('vat_number', _('Partita IVA')),
    ('tax_code', _('Codice fiscale')),
    ('sdi_code', _('Codice destinatario SDI')),
    ('pec_email', _('PEC')),
    ('address_street', _('Indirizzo')),
    ('address_city', _('Città')),
    ('address_zip', _('CAP')),
    ('address_province', _('Provincia')),
    ('address_country', _('Paese')),
    ('website', _('Sito web')),
    ('logo_url', _('URL logo')),
    ('business_description', _('Descrizione attività')),
]
CONTACT_FIELDS = [
    ('last_name', _('Cognome')),
    ('first_name', _('Nome')),
    ('email', _('Email')),
    ('phone', _('Telefono')),
    ('job_title', _('Ruolo')),
]


@sponsor_required
def profile_view(request):
    sponsor = request.sponsor
    contact = request.contact

    if request.method == 'POST':
        # --- chiusura del messaggio di benvenuto (primo accesso) ---
        if request.POST.get('azione') == 'dismiss_welcome':
            if contact.welcome_seen_at is None:
                from django.utils import timezone
                contact.welcome_seen_at = timezone.now()
                contact.save(update_fields=['welcome_seen_at', 'updated_at'])
            return redirect('portal:profile')

        # --- aggiunta di un nuovo contatto aziendale ---
        if request.POST.get('azione') == 'add_contact':
            from sponsors.models import Contact
            nome = request.POST.get('nuovo_full_name', '').strip()
            email = request.POST.get('nuovo_email', '').strip()
            if not nome or not email:
                messages.error(request, "Per aggiungere un contatto servono almeno nome ed email.")
                return redirect('portal:profile')
            ruoli = request.POST.getlist('nuovo_roles')
            ruoli_validi = [r for r, _ in CONTACT_ROLE_CHOICES]
            ruoli = [r for r in ruoli if r in ruoli_validi]
            _nl = (request.POST.get('nuovo_preferred_language') or '').strip()
            nuovo_lang = _nl if _nl in ('it', 'en') else 'it'
            try:
                nuovo = Contact(
                    sponsor=sponsor,
                    full_name=nome,
                    email=email,
                    phone=request.POST.get('nuovo_phone', '').strip(),
                    job_title=request.POST.get('nuovo_job_title', '').strip(),
                    roles=ruoli,
                    preferred_language=nuovo_lang,
                    has_portal_access=False,
                )
                # Validazione (email univoca per persona: vedi Contact.clean)
                from django.core.exceptions import ValidationError
                try:
                    nuovo.clean()
                except ValidationError as ve:
                    for msgs in ve.message_dict.values():
                        for m in msgs:
                            messages.error(request, m)
                    return redirect('portal:profile')
                nuovo.save()
                messages.success(request, f"Contatto '{nome}' aggiunto.")
                logger.info("Nuovo contatto aggiunto da sponsor %s: %s", sponsor.id, email)
            except Exception as e:
                logger.exception("Errore creazione contatto sponsor %s", sponsor.id)
                messages.error(request, f"Errore nell'aggiunta del contatto: {e}")
            return redirect('portal:profile')

        # --- cambio lingua preferita di un contatto esistente (bandierina) ---
        if request.POST.get('azione') == 'set_contact_language':
            from sponsors.models import Contact
            cid = (request.POST.get('contact_id') or '').strip()
            _lang = (request.POST.get('preferred_language') or '').strip()
            target = Contact.objects.filter(sponsor=sponsor, id=cid).first() if cid else None
            if not target or _lang not in ('it', 'en'):
                messages.error(request, "Impossibile aggiornare la lingua del contatto.")
            else:
                target.preferred_language = _lang
                target.save(update_fields=['preferred_language'])
                messages.success(request, "Lingua di '%s' aggiornata." % target.full_name)
            return redirect('portal:profile')

        # --- rimozione di un contatto aziendale (referente che ha lasciato l'azienda) ---
        if request.POST.get('azione') == 'remove_contact':
            from sponsors.models import Contact
            cid = (request.POST.get('contact_id') or '').strip()
            target = Contact.objects.filter(sponsor=sponsor, id=cid).first() if cid else None
            if not target:
                messages.error(request, "Contatto non trovato.")
            elif target.id == contact.id:
                messages.error(request, "Non puoi rimuovere il tuo stesso contatto.")
            else:
                nome_rim = target.full_name
                try:
                    target.delete()  # soft-delete
                    messages.success(request, "Contatto '%s' rimosso." % nome_rim)
                    logger.info("Contatto %s rimosso da sponsor %s", target.id, sponsor.id)
                except Exception as e:
                    logger.exception("Errore rimozione contatto sponsor %s", sponsor.id)
                    messages.error(request, "Errore nella rimozione: %s" % e)
            return redirect('portal:profile')

        # aggiorna sponsor
        for field, _label in SPONSOR_FIELDS:
            if hasattr(sponsor, field):
                val = request.POST.get(f'sponsor_{field}', '').strip()
                setattr(sponsor, field, val)
        # domanda "Azienda farmaceutica": flag + Codice SIS (mostrato solo se flaggato)
        sponsor.is_pharma_company = request.POST.get('sponsor_is_pharma_company') == 'on'
        sponsor.sis_code = request.POST.get('sponsor_sis_code', '').strip()
        # aggiorna contatto
        for field, _label in CONTACT_FIELDS:
            if hasattr(contact, field):
                val = request.POST.get(f'contact_{field}', '').strip()
                # email/cognome non li svuotiamo se arrivano vuoti per errore
                if field in ('email', 'last_name') and not val:
                    continue
                setattr(contact, field, val)
        # lingua preferita (scelta con le bandierine)
        _lang = (request.POST.get('contact_preferred_language') or '').strip()
        if _lang in ('it', 'en'):
            contact.preferred_language = _lang
        # logo caricato (opzionale)
        logo_caricato = request.FILES.get('sponsor_logo_file')
        if logo_caricato:
            try:
                compresso = _comprimi_logo(logo_caricato)
                nome = f"logo_{sponsor.id}.png"
                sponsor.logo_file.save(nome, compresso, save=False)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('portal:profile')
            except Exception as e:
                logger.exception("Errore compressione logo sponsor %s", sponsor.id)
                messages.error(request, f"Errore nel caricamento del logo: {e}")
                return redirect('portal:profile')
        # Al primo salvataggio l'utente ha completato l'onboarding: chiudo il
        # messaggio di benvenuto se non l'ha gia' fatto col pulsante.
        if contact.welcome_seen_at is None:
            from django.utils import timezone
            contact.welcome_seen_at = timezone.now()
        # Ritorno automatico (es. alla conferma del preventivo che ha
        # rimandato qui il cliente): solo URL interni.
        next_url = (request.POST.get('next') or '').strip()
        if next_url and not url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}):
            next_url = ''
        try:
            sponsor.save()
            contact.save()
            logger.info("Profilo aggiornato da sponsor %s", sponsor.id)
        except Exception as e:
            logger.exception("Errore salvataggio profilo sponsor %s", sponsor.id)
            messages.error(request, f"Errore nel salvataggio: {e}")
            return redirect('portal:profile')
        if next_url:
            ancora_mancanti = sponsor.campi_anagrafica_mancanti()
            if not ancora_mancanti:
                messages.success(
                    request,
                    "Anagrafica completa. Ora puoi confermare il preventivo.")
                return redirect(next_url)
            messages.warning(
                request,
                "Dati salvati, ma per confermare il preventivo mancano ancora: "
                + ", ".join(ancora_mancanti) + ".")
            return redirect(f"{reverse('portal:profile')}?next={next_url}")
        messages.success(request, "Dati aggiornati correttamente.")
        return redirect('portal:profile')

    # GET: costruisco i campi con valori attuali
    from sponsors.models import Sponsor as _Sponsor
    _required = {f for f, _ in _Sponsor.PROFILO_OBBLIGATORIO}
    _help = {
        'business_description': _("Indicare se produttore o distributore e la "
                                  "tipologia generica di prodotti trattati."),
    }
    sponsor_fields = [
        {'name': f'sponsor_{f}', 'label': lbl, 'value': getattr(sponsor, f, '') or '',
         'required': f in _required, 'help': _help.get(f, '')}
        for f, lbl in SPONSOR_FIELDS if hasattr(sponsor, f)
    ]
    contact_fields = [
        {'name': f'contact_{f}', 'label': lbl, 'value': getattr(contact, f, '') or ''}
        for f, lbl in CONTACT_FIELDS if hasattr(contact, f)
    ]
    # contatti aziendali esistenti (tutti i Contact dello sponsor)
    try:
        contatti = list(sponsor.contacts.all())
    except Exception:
        from sponsors.models import Contact
        contatti = list(Contact.objects.filter(sponsor=sponsor))

    # Ordine alfabetico per cognome (ultima parola del nome completo)
    def _cognome(c):
        parti = (c.full_name or '').strip().split()
        return (parti[-1].lower() if parti else '', (c.full_name or '').lower())
    contatti.sort(key=_cognome)

    role_labels = dict(CONTACT_ROLE_CHOICES)
    contatti_view = []
    for c in contatti:
        ruoli_txt = ", ".join(str(role_labels.get(r, r)) for r in (c.roles or []))
        contatti_view.append({
            'id': c.id,
            'is_self': (c.id == contact.id),
            'full_name': c.full_name,
            'email': c.email,
            'phone': getattr(c, 'phone', '') or '',
            'job_title': getattr(c, 'job_title', '') or '',
            'ruoli': ruoli_txt,
            'preferred_language': getattr(c, 'preferred_language', 'it') or 'it',
        })

    manca_operativo = not any('operational' in (c.roles or []) for c in contatti)

    # URL interno a cui tornare dopo il salvataggio (es. conferma preventivo)
    next_url = (request.GET.get('next') or '').strip()
    if next_url and not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}):
        next_url = ''

    return render(request, 'portal/profile/edit.html', {
        'next_url': next_url,
        'sponsor': sponsor,
        'contact': contact,
        'sponsor_fields': sponsor_fields,
        'contact_fields': contact_fields,
        'contatti': contatti_view,
        'role_choices': CONTACT_ROLE_CHOICES,
        'manca_operativo': manca_operativo,
        # Benvenuto solo al primo accesso (finche' non l'ha visto/chiuso).
        'show_welcome': contact.welcome_seen_at is None,
    })
