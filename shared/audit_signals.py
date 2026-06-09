"""Audit delle modifiche fatte DAL PORTALE (le modifiche dal backoffice sono
gia' nel LogEntry di Django). Scrive su AuditLog: chi, cosa, quando, IP."""
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from core.middleware import get_current_request

# Modelli tracciati -> campi di cui registrare le variazioni
TRACKED = {
    'Contact': ['first_name', 'last_name', 'email', 'phone', 'job_title',
                'preferred_language', 'marketing_consent', 'roles'],
    'Sponsor': ['legal_name', 'vat_number', 'tax_code', 'sdi_code', 'pec_email',
                'address_street', 'address_city', 'address_zip', 'address_province',
                'address_country', 'website', 'business_description'],
}


def _val(v):
    """Valore serializzabile in JSON."""
    if v is None or isinstance(v, (str, int, float, bool, list, dict)):
        return v
    return str(v)


def _portal_request():
    """Richiesta corrente SE proviene dal portale (non backoffice)."""
    req = get_current_request()
    if req is None:
        return None
    path = getattr(req, 'path', '') or ''
    if not path.startswith('/portal/'):
        return None
    user = getattr(req, 'user', None)
    if not (user and getattr(user, 'is_authenticated', False)):
        return None
    return req


def _client_meta(req):
    ip = (req.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
          or req.META.get('REMOTE_ADDR'))
    ua = (req.META.get('HTTP_USER_AGENT', '') or '')[:500]
    return (ip or None), ua


@receiver(pre_save)
def _stash_old(sender, instance, **kwargs):
    name = sender.__name__
    if name not in TRACKED or not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
        instance._audit_old = {f: getattr(old, f, None) for f in TRACKED[name]}
    except sender.DoesNotExist:
        instance._audit_old = None


def _write(req, action, instance, changes):
    from .models import AuditLog
    ip, ua = _client_meta(req)
    try:
        AuditLog.objects.create(
            user=req.user, action=action,
            entity_type=type(instance).__name__,
            entity_id=getattr(instance, 'pk', None),
            changes=changes or None, ip_address=ip, user_agent=ua,
        )
    except Exception:
        pass  # l'audit non deve mai bloccare l'operazione


@receiver(post_save)
def _log_save(sender, instance, created, **kwargs):
    name = sender.__name__
    if name not in TRACKED:
        return
    req = _portal_request()
    if req is None:
        return
    if created:
        changes = {f: [None, _val(getattr(instance, f, None))] for f in TRACKED[name]}
        _write(req, 'create', instance, changes)
        return
    old = getattr(instance, '_audit_old', None) or {}
    changes = {}
    for f in TRACKED[name]:
        nv = getattr(instance, f, None)
        if _val(old.get(f)) != _val(nv):
            changes[f] = [_val(old.get(f)), _val(nv)]
    if changes:
        _write(req, 'update', instance, changes)


@receiver(post_delete)
def _log_delete(sender, instance, **kwargs):
    if sender.__name__ not in TRACKED:
        return
    req = _portal_request()
    if req is None:
        return
    _write(req, 'delete', instance, None)
