"""Vista profilo: lo sponsor modifica la propria anagrafica."""
import logging
from io import BytesIO

from django.contrib import messages
from django.core.files.base import ContentFile
from django.shortcuts import redirect, render

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

logger = logging.getLogger(__name__)

# Ruoli funzionali disponibili (value, label)
CONTACT_ROLE_CHOICES = [
    ('signer', 'Firmatario'),
    ('marketing', 'Marketing'),
    ('finance', 'Amministrazione'),
    ('operational', 'Operativo'),
    ('cc', 'CC'),
    ('educational', 'Educational manager'),
]

# Campi modificabili (nome_campo_modello -> etichetta)
SPONSOR_FIELDS = [
    ('legal_name', 'Ragione sociale'),
    ('vat_number', 'Partita IVA'),
    ('tax_code', 'Codice fiscale'),
    ('sdi_code', 'Codice destinatario SDI'),
    ('pec_email', 'PEC'),
    ('address_street', 'Indirizzo'),
    ('address_city', 'Città'),
    ('address_zip', 'CAP'),
    ('address_province', 'Provincia'),
    ('address_country', 'Paese'),
    ('website', 'Sito web'),
    ('logo_url', 'URL logo'),
    ('business_description', 'Descrizione attività'),
]
CONTACT_FIELDS = [
    ('full_name', 'Nome e cognome'),
    ('email', 'Email'),
    ('phone', 'Telefono'),
    ('job_title', 'Ruolo'),
]


@sponsor_required
def profile_view(request):
    sponsor = request.sponsor
    contact = request.contact

    if request.method == 'POST':
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
            try:
                Contact.objects.create(
                    sponsor=sponsor,
                    full_name=nome,
                    email=email,
                    phone=request.POST.get('nuovo_phone', '').strip(),
                    job_title=request.POST.get('nuovo_job_title', '').strip(),
                    roles=ruoli,
                    has_portal_access=False,
                )
                messages.success(request, f"Contatto '{nome}' aggiunto.")
                logger.info("Nuovo contatto aggiunto da sponsor %s: %s", sponsor.id, email)
            except Exception as e:
                logger.exception("Errore creazione contatto sponsor %s", sponsor.id)
                messages.error(request, f"Errore nell'aggiunta del contatto: {e}")
            return redirect('portal:profile')

        # aggiorna sponsor
        for field, _label in SPONSOR_FIELDS:
            if hasattr(sponsor, field):
                val = request.POST.get(f'sponsor_{field}', '').strip()
                setattr(sponsor, field, val)
        # aggiorna contatto
        for field, _label in CONTACT_FIELDS:
            if hasattr(contact, field):
                val = request.POST.get(f'contact_{field}', '').strip()
                # email/full_name non li svuotiamo se arrivano vuoti per errore
                if field in ('email', 'full_name') and not val:
                    continue
                setattr(contact, field, val)
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
        try:
            sponsor.save()
            contact.save()
            messages.success(request, "Dati aggiornati correttamente.")
            logger.info("Profilo aggiornato da sponsor %s", sponsor.id)
        except Exception as e:
            logger.exception("Errore salvataggio profilo sponsor %s", sponsor.id)
            messages.error(request, f"Errore nel salvataggio: {e}")
        return redirect('portal:profile')

    # GET: costruisco i campi con valori attuali
    sponsor_fields = [
        {'name': f'sponsor_{f}', 'label': lbl, 'value': getattr(sponsor, f, '') or ''}
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

    role_labels = dict(CONTACT_ROLE_CHOICES)
    contatti_view = []
    for c in contatti:
        ruoli_txt = ", ".join(role_labels.get(r, r) for r in (c.roles or []))
        contatti_view.append({
            'full_name': c.full_name,
            'email': c.email,
            'phone': getattr(c, 'phone', '') or '',
            'job_title': getattr(c, 'job_title', '') or '',
            'ruoli': ruoli_txt,
        })

    return render(request, 'portal/profile/edit.html', {
        'sponsor': sponsor,
        'contact': contact,
        'sponsor_fields': sponsor_fields,
        'contact_fields': contact_fields,
        'contatti': contatti_view,
        'role_choices': CONTACT_ROLE_CHOICES,
    })
