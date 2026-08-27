"""
Service per invitare contatti al portale sponsor.

Crea un User collegato al Contact, genera password temporanea, manda email
di invito con credenziali.

Usato da:
- Azione admin "Invita al portale" sul Contact
- Management command 'invite_sponsor' (per invio massivo da CLI)
"""
import logging
import secrets
import string

from django.contrib.auth import get_user_model
from django.db import transaction

from sponsors.models import Contact

logger = logging.getLogger(__name__)
User = get_user_model()


def generate_temp_password(length=12):
    """Genera password temporanea sicura ma leggibile."""
    # Esclude caratteri ambigui (0, O, l, 1, I)
    alphabet = ''.join(c for c in (string.ascii_letters + string.digits)
                       if c not in '0OlI1')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@transaction.atomic
def invite_contact_to_portal(contact: Contact, send_email: bool = True):
    """
    Invita un Contact al portale: crea User, manda email con credenziali.
    
    Args:
        contact: istanza Contact
        send_email: se False, non manda l'email (solo crea l'User).
                    Utile per testing o se vuoi mandare l'email a mano.
    
    Returns:
        tuple (user, temp_password, was_created)
        was_created=True se l'User è stato creato ora, False se esisteva già
    
    Raises:
        ValueError se il Contact non ha email
    """
    if not contact.email:
        raise ValueError(
            f"Contact {contact.full_name} non ha un'email, impossibile invitare."
        )

    # Utente gia' esistente per questo contatto o per questa email
    user = None
    if contact.portal_user_id:
        user = contact.portal_user
    if user is None:
        user = User.objects.filter(email__iexact=contact.email).first()

    # PROTEZIONE: mai usare come accesso cliente l'email di un account del
    # BACKOFFICE (prima l'invito lo declassava a 'sponsor' e ne resettava la
    # password; e comunque il portale respinge i non-sponsor con 'Ci siamo quasi').
    if user is not None and (user.is_staff or user.is_superuser
                             or getattr(user, 'role', 'sponsor') != 'sponsor'):
        raise ValueError(
            f"l'email {contact.email} appartiene a un account OPERATORE del "
            "backoffice e non può essere usata come accesso cliente al portale. "
            "Registra il contatto con un'email diversa."
        )

    if user is not None:
        if user.last_login:
            # Ha GIA' usato il portale (es. per un altro congresso): le sue
            # credenziali restano valide, NON tocchiamo la password. Colleghiamo
            # solo il contatto; nessuna email di invito (per rimandare le
            # credenziali c'e' l'azione 'Invia email di RESET PASSWORD').
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
            contact.has_portal_access = True
            contact.portal_user = user
            contact.save(update_fields=['has_portal_access', 'portal_user', 'updated_at'])
            logger.info("Invito: %s ha gia' un accesso attivo, credenziali invariate", user.email)
            return user, None, False
        # Mai entrato: rigenera la password temporanea e reinvia le credenziali
        temp_password = generate_temp_password()
        user.set_password(temp_password)
        user.is_active = True
        user.save(update_fields=['password', 'is_active'])
        was_created = False
    else:
        # Crea nuovo User
        temp_password = generate_temp_password()
        user = User.objects.create_user(
            username=contact.email,
            email=contact.email,
            password=temp_password,
            first_name=contact.first_name or _extract_first_name(contact.full_name),
            last_name=contact.last_name or _extract_last_name(contact.full_name),
            role='sponsor',
            is_active=True,
        )
        was_created = True

    # Collega il Contact all'User
    contact.has_portal_access = True
    contact.portal_user = user
    contact.save(update_fields=['has_portal_access', 'portal_user', 'updated_at'])

    # Manda email
    if send_email:
        _send_invitation_email(user, contact, temp_password)

    logger.info(
        "Sponsor invitato: contact=%s user=%s created=%s",
        contact.id, user.id, was_created
    )

    return user, temp_password, was_created


def _send_invitation_email(user, contact, temp_password):
    """Manda email con credenziali di accesso."""
    from contracts.services.email_sender import send_email
    from django.conf import settings

    portal_url = getattr(settings, 'PORTAL_URL', '/portal/')

    lang = contact.preferred_language or 'it'
    subject = ("Welcome to the sponsor portal · your login credentials"
               if lang == 'en'
               else "Benvenuto nel portale sponsor · credenziali di accesso")

    try:
        send_email(
            template_name='portal_invitation',
            context={
                'user': user,
                'contact': contact,
                'temp_password': temp_password,
                'portal_url': portal_url,
            },
            to=[contact.email],
            subject=subject,
            language=lang,
            related_to=contact,
            communication_type='manual',
            is_automated=False,
        )
    except Exception as e:
        logger.exception("Errore invio invito a %s", contact.email)
        raise


def _extract_first_name(full_name: str) -> str:
    """Estrae nome dal full_name (prima parola)."""
    parts = (full_name or '').strip().split()
    return parts[0] if parts else ''


def _extract_last_name(full_name: str) -> str:
    """Estrae cognome dal full_name (resto dopo prima parola)."""
    parts = (full_name or '').strip().split()
    return ' '.join(parts[1:]) if len(parts) > 1 else ''
