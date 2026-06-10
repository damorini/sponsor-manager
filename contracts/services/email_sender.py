"""
Service per rendering e invio email transazionali.

Funzioni principali:
- send_email(template_name, context, to, ...): invio singolo
- get_template_for_language(template_name, language): risolve il path del template
- log_communication(...): salva il record Communication

Flow tipico:
    from contracts.services.email_sender import send_email
    
    send_email(
        template_name='deadline_reminder',
        context={'contact': contact, 'deadline': deadline, ...},
        to=[contact.email],
        language='it',
        related_to=deadline,  # per linkare la Communication
    )

Provider supportati:
- Postmark (raccomandato)
- Brevo (ex Sendinblue)
- SMTP generico (anche fallback per development)

In development le email vanno sulla console (vedi settings.development).
"""
import logging
from typing import Optional

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


# ============================================================================
# Risoluzione template
# ============================================================================

def get_template_path(template_name: str, language: str = 'it') -> str:
    """
    Restituisce il path del template Django da usare.
    
    Es: ('deadline_reminder', 'en') → 'shared/email_templates/en/deadline_reminder.html'
    
    Fallback: se il template nella lingua richiesta non esiste, ripiega su 'it'.
    """
    primary = f"shared/email_templates/{language}/{template_name}.html"
    fallback = f"shared/email_templates/it/{template_name}.html"

    # Verifica esistenza usando il template engine
    from django.template.loader import get_template
    from django.template import TemplateDoesNotExist

    try:
        get_template(primary)
        return primary
    except TemplateDoesNotExist:
        try:
            get_template(fallback)
            logger.warning(
                "Template %s non trovato in %s, uso fallback italiano",
                template_name, language
            )
            return fallback
        except TemplateDoesNotExist as e:
            raise ValueError(
                f"Template email non trovato: né {primary} né {fallback}"
            ) from e


# ============================================================================
# Costruzione contesto comune
# ============================================================================

def build_common_context(extra_context: dict = None, language: str = 'it') -> dict:
    """
    Aggiunge al contesto le variabili comuni di branding/footer.
    
    Variabili sempre disponibili nei template:
    - language
    - subject (impostato dal chiamante)
    - organizer_name, organizer_address, support_email
    - brand_logo_url, brand_primary_color
    - portal_url, admin_url, checkout_url
    """
    extra_context = extra_context or {}

    # Dati segreteria dal pannello admin (fallback ai settings)
    try:
        from core.models import OrganizerSettings
        _org = OrganizerSettings.load()
    except Exception:
        _org = None

    common = {
        'language': language,
        'organizer_name': getattr(
            settings, 'ORGANIZER_DISPLAY_NAME',
            getattr(settings, 'DEFAULT_ORGANIZER_LEGAL_NAME', 'Sponsor Manager')
        ),
        'organizer_address': getattr(settings, 'ORGANIZER_ADDRESS', ''),
        'support_email': getattr(settings, 'SUPPORT_EMAIL', settings.DEFAULT_FROM_EMAIL),
        'site_url': getattr(settings, 'SITE_URL', '').rstrip('/'),
        'org_name': (_org.name if _org and _org.name else None) or getattr(settings, 'ORGANIZER_DISPLAY_NAME', ''),
        'org_address': (_org.address if _org else '') ,
        'org_email': (_org.email if _org else '') ,
        'org_phone': (_org.phone if _org else '') ,
        'org_website': (_org.website if _org else '') ,
        'org_vat': (_org.vat_number if _org else '') ,
        'org_rea': (_org.rea if _org else '') ,
        'org_logo_url': ((getattr(settings, 'SITE_URL', '').rstrip('/') + _org.logo.url) if (_org and _org.logo) else ''),
        'brand_logo_url': getattr(settings, 'BRAND_LOGO_URL', ''),
        'brand_primary_color': getattr(settings, 'BRAND_PRIMARY_COLOR', '#1d6534'),
        'portal_url': getattr(settings, 'PORTAL_URL', '/portal/'),
        'admin_url': getattr(settings, 'ADMIN_URL', '/admin/'),
        'checkout_url': getattr(settings, 'PORTAL_URL', '/portal/') + 'checkout/',
    }

    # Il context custom prevale (può sovrascrivere se serve)
    common.update(extra_context)
    return common


# ============================================================================
# Invio email
# ============================================================================

def send_plain_email(subject, body, recipients, fail_silently=True):
    """Invia un'email di TESTO SEMPLICE usando la connessione SMTP configurata
    dal pannello (core.models.EmailSettings) — la stessa di tutte le altre
    email dell'app. Se il pannello non e' configurato, ricade sul backend di
    default (console in produzione). Ritorna il numero di email inviate.

    Da usare al posto del send_mail nudo di Django per le notifiche interne:
    quello bypassa il pannello e in prod non recapita nulla."""
    from django.conf import settings
    from django.core.mail import send_mail
    if not recipients:
        return 0
    conn = None
    from_email = settings.DEFAULT_FROM_EMAIL
    try:
        from core.models import EmailSettings
        es = EmailSettings.load()
        conn = es.get_connection()  # None se il pannello non e' abilitato
        if conn is not None and es.from_full:
            from_email = es.from_full
    except Exception:
        conn = None
    return send_mail(subject, body, from_email, recipients,
                     connection=conn, fail_silently=fail_silently)


def send_email(
    template_name: str,
    context: dict,
    to: list,
    subject: str,
    cc: list = None,
    bcc: list = None,
    language: str = 'it',
    attachments: list = None,
    related_to=None,
    communication_type: str = 'manual',
    triggered_by_user=None,
    is_automated: bool = False,
    custom_body_html: str = None,
) -> 'Communication':
    """
    Invia un'email transazionale renderizzando il template specificato.
    
    Args:
        template_name: nome template (es. 'deadline_reminder', SENZA path/.html)
        context: dict di variabili passate al template
        to: lista email destinatari
        subject: oggetto email
        cc, bcc: liste opzionali
        language: lingua per scelta template ('it' o 'en')
        attachments: lista di tuple (filename, content_bytes, mime_type)
        related_to: istanza modello a cui legare la Communication (opzionale)
        communication_type: tipo (es. 'reminder', 'payment_confirmation')
        triggered_by_user: User che ha avviato l'invio (None per automazioni)
        is_automated: True se inviata da task Celery automatico
    
    Returns:
        Istanza Communication salvata nel DB.
    
    Raises:
        ValueError, RuntimeError in caso di problemi.
    """
    from shared.models import Communication, CommunicationStatus

    # 2. Costruisci contesto completo
    full_context = build_common_context(context, language)
    full_context['subject'] = subject

    # 3. Renderizza il body HTML.
    #    Se e' passato un corpo libero (email singola scritta a mano) lo si
    #    avvolge nel layout; altrimenti EmailTemplate attivo o file su disco.
    if custom_body_html is not None:
        body_html = _render_custom_body(custom_body_html, full_context)
    else:
        body_html, subject_override = _render_email_body(
            template_name, language, full_context
        )
        if subject_override:
            subject = subject_override
            full_context['subject'] = subject
    body_text = strip_tags(body_html)  # versione testuale fallback

    # 4. Crea record Communication PRIMA dell'invio (status='queued')
    communication = _create_communication(
        related_to=related_to,
        communication_type=communication_type,
        recipients_to=to,
        recipients_cc=cc or [],
        recipients_bcc=bcc or [],
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        triggered_by_user=triggered_by_user,
        is_automated=is_automated,
    )

    # 5. Costruisci e invia email
    # Connessione e mittente: se c'è una configurazione SMTP da pannello, usala;
    # altrimenti i dati di sistema (.env / settings).
    _conn = None
    _from = settings.DEFAULT_FROM_EMAIL
    try:
        from core.models import EmailSettings
        _es = EmailSettings.load()
        _conn = _es.get_connection()  # None se non abilitata
        if _conn is not None and _es.from_full:
            _from = _es.from_full
    except Exception:
        _conn = None
    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=_from,
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            reply_to=[_from],
            connection=_conn,
        )
        email.attach_alternative(body_html, 'text/html')

        # Allegati: lista di (filename, content, mime_type)
        for attachment in (attachments or []):
            email.attach(*attachment)

        email.send(fail_silently=False)

        # Aggiorna Communication a 'sent'
        communication.status = CommunicationStatus.SENT
        communication.sent_at = timezone.now()
        communication.save(update_fields=['status', 'sent_at', 'updated_at'])

        logger.info(
            "Email inviata: template=%s to=%s subject=%s",
            template_name, to, subject
        )

    except Exception as e:
        # Aggiorna Communication a 'failed'
        communication.status = CommunicationStatus.FAILED
        communication.bounced_at = timezone.now()
        communication.bounce_reason = str(e)[:500]
        communication.save(update_fields=[
            'status', 'bounced_at', 'bounce_reason', 'updated_at'
        ])
        logger.exception("Errore invio email %s a %s", template_name, to)
        raise

    return communication


def _create_communication(
    related_to,
    communication_type,
    recipients_to,
    recipients_cc,
    recipients_bcc,
    subject,
    body_text,
    body_html,
    triggered_by_user,
    is_automated,
):
    """Crea il record Communication (separato per leggibilità)."""
    from shared.models import Communication, CommunicationChannel, CommunicationStatus

    kwargs = {
        'channel': CommunicationChannel.EMAIL,
        'communication_type': communication_type,
        'recipients_to': recipients_to,
        'recipients_cc': recipients_cc,
        'recipients_bcc': recipients_bcc,
        'subject': subject,
        'body_text': body_text,
        'body_html': body_html,
        'status': CommunicationStatus.QUEUED,
        'triggered_by_user': triggered_by_user,
        'is_automated': is_automated,
    }

    if related_to is not None:
        kwargs['content_type'] = ContentType.objects.get_for_model(related_to)
        kwargs['object_id'] = related_to.id

    return Communication.objects.create(**kwargs)


# ============================================================================
# Helper: scelta destinatari per ruolo
# ============================================================================

def get_recipients_for_contract(contract, roles: list = None) -> list:
    """
    Restituisce le email dei contatti dello sponsor che hanno almeno uno dei
    ruoli richiesti.
    
    Es:
        emails = get_recipients_for_contract(contract, roles=['marketing', 'operational'])
    
    Se roles è None, restituisce solo il contatto primario.
    """
    contacts = contract.sponsor.contacts.all()

    if roles:
        # Filtra contatti con almeno uno dei ruoli richiesti
        result = []
        for contact in contacts:
            if any(r in (contact.roles or []) for r in roles):
                if contact.email and contact.email not in result:
                    result.append(contact.email)
        if result:
            return result

    # Fallback: contatto primario o primo disponibile
    primary = contacts.filter(is_primary=True).first()
    if primary and primary.email:
        return [primary.email]

    first = contacts.first()
    if first and first.email:
        return [first.email]

    return []


def get_signer_email(contract) -> Optional[str]:
    """Email del firmatario del contratto, se valorizzato."""
    if contract.sponsor_signer_contact and contract.sponsor_signer_contact.email:
        return contract.sponsor_signer_contact.email
    return None


# ============================================================================
# Override dei template email dall'admin (modello EmailTemplate)
# ============================================================================

def _pick_lang(raw, language):
    """Estrae la lingua da un valore bilingue {it,en}. Accetta un dict (campo
    JSONField), una stringa JSON, o una vecchia repr Python; se e' testo
    semplice lo restituisce cosi' com'e'."""
    if not raw:
        return ''

    def _from_dict(data):
        return (data.get(language) or data.get('it')
                or next((v for v in data.values() if v), ''))

    if isinstance(raw, dict):
        return _from_dict(raw)
    # stringhe legacy: prova JSON valido, poi repr Python ({'it': ...})
    import json
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return _from_dict(data)
    except (ValueError, TypeError):
        pass
    try:
        import ast
        data = ast.literal_eval(raw)
        if isinstance(data, dict):
            return _from_dict(data)
    except (ValueError, SyntaxError, TypeError):
        pass
    return raw


def _render_email_body(template_name, language, context):
    """
    Ritorna (body_html, subject_override).
    Se esiste un EmailTemplate attivo con code == template_name, usa il testo
    dall'admin avvolto nel layout grafico email_base.html. Altrimenti (o in caso
    di errore) ripiega sul file su disco. subject_override e' None se non
    sovrascritto dall'admin.
    """
    tpl = None
    try:
        from shared.models import EmailTemplate
        tpl = EmailTemplate.objects.filter(
            code=template_name, is_active=True
        ).first()
    except Exception:
        tpl = None

    if tpl:
        try:
            from django.template import engines
            from django.utils.html import linebreaks
            dj = engines['django']

            body_src = _pick_lang(tpl.body_template, language)
            subj_src = _pick_lang(tpl.subject_template, language)

            # pass 1: risolve i placeholder DENTRO il corpo
            body_resolved = dj.from_string(body_src).render(context)
            # se il corpo e' testo semplice (nessun tag HTML), converte gli a-capo
            if '<' not in (body_src or ''):
                body_resolved = linebreaks(body_resolved)

            # pass 2: avvolge il corpo nel layout grafico condiviso
            wrap_ctx = dict(context)
            wrap_ctx['email_body_html'] = body_resolved
            body_html = render_to_string(
                'shared/email_templates/base/_db_wrapper.html', wrap_ctx
            )

            subject_override = None
            if subj_src:
                subject_override = dj.from_string(subj_src).render(context).strip()
            return body_html, subject_override
        except Exception:
            logger.exception(
                "Errore nel rendering EmailTemplate '%s' dall'admin: uso il file",
                template_name,
            )

    # fallback: file su disco (comportamento storico)
    template_path = get_template_path(template_name, language)
    return render_to_string(template_path, context), None


def _render_custom_body(body_src, context):
    """Avvolge un corpo libero (HTML o testo semplice) nel layout email_base,
    risolvendo i placeholder. Usato per le email singole scritte a mano."""
    from django.template import engines
    from django.utils.html import linebreaks
    dj = engines['django']
    body_resolved = dj.from_string(body_src or '').render(context)
    if '<' not in (body_src or ''):
        body_resolved = linebreaks(body_resolved)
    wrap_ctx = dict(context)
    wrap_ctx['email_body_html'] = body_resolved
    return render_to_string('shared/email_templates/base/_db_wrapper.html', wrap_ctx)
