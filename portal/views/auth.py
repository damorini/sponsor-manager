"""
View di autenticazione del portale sponsor.

Login: usa il backend Django standard, ma valida che l'utente abbia
ruolo SPONSOR (non far accedere admin/operator dal portale).

Password reset: stesso flusso Django, con email custom dal nostro template.
"""
import logging

from django.contrib import messages
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import (
    PasswordResetForm, SetPasswordForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from users.models import User

logger = logging.getLogger(__name__)


# ============================================================================
# Login
# ============================================================================

@csrf_protect
@never_cache
@require_http_methods(['GET', 'POST'])
def login_view(request):
    """Login portale: solo per User con role=SPONSOR."""
    if request.user.is_authenticated:
        return redirect('portal:dashboard')

    next_url = request.GET.get('next', '') or request.POST.get('next', '')
    # Anti open-redirect: accetta solo destinazioni interne. startswith('/')
    # lasciava passare gli URL protocol-relative (//sito-esterno.com).
    from django.utils.http import url_has_allowed_host_and_scheme
    if next_url and not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}):
        next_url = ''

    if request.method == 'POST':
        email = request.POST.get('username', '').strip().lower()
        password = request.POST.get('password', '')

        if not email or not password:
            return render(request, 'portal/auth/login.html', {
                'form': {'errors': True},
                'next': next_url,
            })

        # Cerca user per email (Django auth usa username, ma gli sponsor
        # si registrano con email)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None

        if user:
            user = authenticate(request, username=user.email, password=password)

        if user is not None and user.is_active and user.is_sponsor:
            django_login(request, user)
            logger.info("Sponsor login: %s", email)

            # Contatti collegati: 0 = account incompleto; 1 = azienda automatica;
            # 2+ = la stessa persona gestisce piu' aziende -> maschera di scelta.
            from portal.views.dashboard import user_contacts_qs
            contacts = list(user_contacts_qs(user)[:2])
            if not contacts:
                logger.error("User %s sponsor ma senza Contact collegato", user.id)
                django_logout(request)
                messages.error(
                    request,
                    "Account configurato in modo incompleto. Contatta l'assistenza."
                )
                return redirect('portal:login')
            if len(contacts) == 1:
                request.session['active_contact_id'] = str(contacts[0].pk)
            else:
                url = reverse('portal:scegli_azienda')
                if next_url:
                    from urllib.parse import quote
                    url += '?next=' + quote(next_url)
                return redirect(url)

            # Redirect a next (gia' validato sopra) o dashboard
            if next_url:
                return redirect(next_url)
            return redirect('portal:dashboard')
        else:
            return render(request, 'portal/auth/login.html', {
                'form': {'errors': True},
                'next': next_url,
            })

    return render(request, 'portal/auth/login.html', {'next': next_url})


@require_POST
def logout_view(request):
    """Logout: pulisce sessione e redirige a login."""
    django_logout(request)
    messages.success(request, "Sei uscito correttamente.")
    return redirect('portal:login')


# ============================================================================
# Password reset
# ============================================================================

@csrf_protect
@require_http_methods(['GET', 'POST'])
def password_reset_view(request):
    """
    Richiesta reset password: l'utente inserisce email, riceve link.
    
    Per sicurezza non rivela se l'email esiste o no nel sistema (sempre
    mostra "email inviata", anche se l'email non corrisponde a nessun account).
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()

        if email:
            # Qualsiasi utente attivo con quell'email (sponsor del portale,
            # ma anche operatori/admin del backoffice: il link 'Password
            # dimenticata?' della login admin arriva qui).
            users = User.objects.filter(
                email__iexact=email,
                is_active=True,
            )
            for user in users:
                _send_password_reset_email(request, user)

        # Sempre mostra "email inviata" per sicurezza (no user enumeration)
        return redirect('portal:password_reset_done')

    return render(request, 'portal/auth/password_reset.html')


def password_reset_done_view(request):
    """Conferma che l'email di reset è stata inviata."""
    return render(request, 'portal/auth/password_reset_done.html')


@csrf_protect
@never_cache
@require_http_methods(['GET', 'POST'])
def password_reset_confirm_view(request, uidb64, token):
    """
    Click sul link nell'email: l'utente imposta la nuova password.
    """
    user = _get_user_from_uid(uidb64)
    valid_link = (
        user is not None and
        default_token_generator.check_token(user, token)
    )

    if request.method == 'POST' and valid_link:
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            # ricorda dove deve accedere ORA che la password e' cambiata:
            # backoffice per gli operatori, portale per i clienti
            request.session['reset_is_staff'] = bool(
                getattr(user, 'is_staff', False))
            return redirect('portal:password_reset_complete')
    else:
        form = SetPasswordForm(user) if valid_link else None

    return render(request, 'portal/auth/password_reset_confirm.html', {
        'form': form,
        'validlink': valid_link,
    })


def password_reset_complete_view(request):
    """Conferma password aggiornata: il pulsante porta al posto giusto
    (backoffice per gli operatori, portale per i clienti)."""
    is_staff = bool(request.session.pop('reset_is_staff', False))
    return render(request, 'portal/auth/password_reset_complete.html', {
        'is_staff': is_staff,
        'login_url': '/admin/' if is_staff else reverse('portal:login'),
    })


# ============================================================================
# Helper interni
# ============================================================================

def _send_password_reset_email(request, user):
    """Manda email con link di reset password."""
    from contracts.services.email_sender import send_email

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    reset_path = reverse('portal:password_reset_confirm', kwargs={
        'uidb64': uid, 'token': token,
    })
    reset_url = request.build_absolute_uri(reset_path)

    # La pagina per impostare la password e' UNA sola (quella del portale),
    # ma il posto dove si accede DOPO cambia: gli operatori del backoffice
    # entrano da /admin/, i clienti dal portale. Senza questa distinzione
    # l'email mandava un operatore al portale, dove verrebbe respinto.
    is_staff = bool(getattr(user, 'is_staff', False))
    login_url = request.build_absolute_uri(
        '/admin/' if is_staff else reverse('portal:login'))

    lang = getattr(getattr(user, 'contact_profile', None), 'preferred_language', 'it') or 'it'
    if is_staff:
        subject = ("Reset your password · Backoffice" if lang == 'en'
                   else "Reimposta la password · Backoffice")
    else:
        subject = ("Reset your password · Sponsor portal" if lang == 'en'
                   else "Reimposta la password · Portale sponsor")

    try:
        send_email(
            template_name='password_reset',
            context={
                'user': user,
                'reset_url': reset_url,
                'is_staff': is_staff,
                'login_url': login_url,
            },
            to=[user.email],
            subject=subject,
            language=lang,
            related_to=None,
            communication_type='manual',
            is_automated=True,
        )
    except Exception as e:
        logger.exception("Errore invio reset email a %s", user.email)


def _get_user_from_uid(uidb64):
    """Decodifica uidb64 e restituisce User, o None."""
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        # Qualsiasi utente attivo: la richiesta di reset invia l'email anche
        # a operatori/admin del backoffice, quindi il link deve valere per loro.
        return User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None

@login_required
def password_change_view(request):
    """Cambio password per il cliente loggato."""
    from django.contrib.auth.forms import PasswordChangeForm
    from django.contrib.auth import update_session_auth_hash
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password aggiornata correttamente.")
            return redirect('portal:profile')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'portal/auth/password_change.html', {'form': form})

@login_required(login_url='portal:login')
def scegli_azienda_view(request):
    """Maschera 'Scegli l'azienda': la stessa persona (stesso login) puo'
    gestire piu' aziende. Qui sceglie quale usare; la scelta resta in sessione
    e si puo' cambiare in ogni momento dal menu ('Cambia azienda')."""
    from portal.views.dashboard import accesso_quasi_fatto, user_contacts_qs

    if not getattr(request.user, 'is_sponsor', False):
        return accesso_quasi_fatto(request)

    contacts = list(user_contacts_qs(request.user))
    if not contacts:
        return accesso_quasi_fatto(request)

    next_url = request.POST.get('next', '') or request.GET.get('next', '')
    # Anti open-redirect (vedi login_view): solo destinazioni interne.
    from django.utils.http import url_has_allowed_host_and_scheme
    if next_url and not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}):
        next_url = ''

    if request.method == 'POST':
        cid = (request.POST.get('contact_id') or '').strip()
        scelto = next((c for c in contacts if str(c.pk) == cid), None)
        if scelto is not None:
            request.session['active_contact_id'] = str(scelto.pk)
            logger.info("Azienda attiva scelta: user=%s sponsor=%s",
                        request.user.id, scelto.sponsor_id)
            if next_url:
                return redirect(next_url)
            return redirect('portal:dashboard')
        messages.error(request, "Scelta non valida, riprova.")

    if len(contacts) == 1:
        request.session['active_contact_id'] = str(contacts[0].pk)
        return redirect('portal:dashboard')

    attiva = request.session.get('active_contact_id')
    return render(request, 'portal/auth/scegli_azienda.html', {
        'contacts': contacts,
        'next': next_url,
        'attiva': attiva,
    })


def impersonate_start(request, sponsor_id):
    """Staff: entra nel portale come il cliente (contatto principale dello sponsor)."""
    from django.contrib.auth import login as dj_login
    from django.http import HttpResponseForbidden
    from django.shortcuts import get_object_or_404
    from sponsors.models import Sponsor
    if not request.user.is_staff:
        return HttpResponseForbidden("Non autorizzato.")
    sponsor = get_object_or_404(Sponsor, pk=sponsor_id)
    qs = sponsor.contacts.filter(has_portal_access=True, portal_user__isnull=False)
    contact = qs.filter(is_primary=True).first() or qs.first()
    if not contact:
        messages.error(request, "Questo sponsor non ha contatti con accesso al portale.")
        return redirect(request.META.get('HTTP_REFERER') or '/admin/sponsors/sponsor/')
    target = contact.portal_user
    staff_pk = request.user.pk
    target.backend = 'django.contrib.auth.backends.ModelBackend'
    dj_login(request, target)
    request.session['impersonator_id'] = str(staff_pk)
    # L'operatore impersona per QUESTO sponsor: azienda attiva gia' scelta
    # (l'utente reale potrebbe gestirne piu' di una).
    request.session['active_contact_id'] = str(contact.pk)
    messages.info(request, "Stai navigando come cliente. Usa il banner in alto per tornare all'amministrazione.")
    return redirect('portal:dashboard')


def impersonate_stop(request):
    """Torna all'amministrazione dopo l'impersonificazione."""
    from django.contrib.auth import login as dj_login
    from users.models import User
    staff_pk = request.session.get('impersonator_id')
    if not staff_pk:
        return redirect('/admin/')
    try:
        staff = User.objects.get(pk=staff_pk, is_staff=True)
    except User.DoesNotExist:
        # logout_view e' POST-only: un redirect GET li' darebbe 405 e
        # l'operatore resterebbe intrappolato nella sessione cliente.
        django_logout(request)
        return redirect('portal:login')
    staff.backend = 'django.contrib.auth.backends.ModelBackend'
    dj_login(request, staff)
    return redirect('/admin/sponsors/sponsor/')
