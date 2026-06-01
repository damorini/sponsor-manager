"""
Visibilita' per-evento nell'admin.

Operatori e "Sola lettura" vedono solo i dati degli eventi abilitati
(User.managed_events). Superuser e Amministratori vedono tutto.
I clienti (anagrafiche/aziende) NON passano da qui: restano visibili a tutti.
"""


def can_see_all(user):
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "can_see_all_events", False)
    )


def scope_by_event(request, qs, event_path):
    """Limita qs agli eventi gestiti dall'utente.

    event_path: percorso ORM verso l'evento, es. 'event', 'contract__event', 'id'.
    """
    user = getattr(request, "user", None)
    if user is None or can_see_all(user):
        return qs
    managed = getattr(user, "managed_events", None)
    if managed is None:
        return qs.none()
    return qs.filter(**{f"{event_path}__in": managed.all()})
