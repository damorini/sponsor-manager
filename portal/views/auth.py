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

            # Verifica che il Contact collegato esista
            try:
                contact = user.contact_profile
            except Exception:
                logger.error("User %s sponsor ma senza Contact collegato", user.id)
                django_logout(request)
                messages.error(
                    request,
                    "Account configurato in modo incompleto. Contatta l'assistenza."
                )
                return redirect('portal:login')

            # Redirect a next o dashboard
            if next_url and next_url.startswith('/'):
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
            # Trova users sponsor con quell'email
            users = User.objects.filter(
                email__iexact=email,
                is_active=True,
                role='sponsor',
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
            return redirect('portal:password_reset_complete')
    else:
        form = SetPasswordForm(user) if valid_link else None

    return render(request, 'portal/auth/password_reset_confirm.html', {
        'form': form,
        'validlink': valid_link,
    })


def password_reset_complete_view(request):
    """Conferma password aggiornata."""
    return render(request, 'portal/auth/password_reset_complete.html')


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

    lang = getattr(getattr(user, 'contact_profile', None), 'preferred_language', 'it') or 'it'
    subject = ("Reset your password · Sponsor portal" if lang == 'en'
               else "Reimposta la password · Portale sponsor")

    try:
        send_email(
            template_name='password_reset',
            context={
                'user': user,
                'reset_url': reset_url,
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
        return User.objects.get(pk=uid, is_active=True, role='sponsor')
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
        return redirect('portal:logout')
    staff.backend = 'django.contrib.auth.backends.ModelBackend'
    dj_login(request, staff)
    return redirect('/admin/sponsors/sponsor/')
