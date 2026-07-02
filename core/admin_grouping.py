"""
Raggruppa le voci del menu admin (sidebar + indice) in SEZIONI LOGICHE invece
dell'elenco per app Django. Si aggancia sovrascrivendo AdminSite.get_app_list
(chiamato sia dalla nav-sidebar sia dall'indice).
"""
import types
from django.contrib import admin

# (Nome sezione, [object_name dei modelli, nell'ordine voluto])
GROUPS = [
    ("\U0001F4C5 Eventi & Spazi", ["Event", "Stand", "StandBlock"]),
    ("\U0001F3E2 Sponsor & Contatti", ["Sponsor", "Contact", "PortalMessage", "Wishlist", "WishlistItem"]),
    ("\U0001F4C4 Contratti & Scadenze", ["Contract", "ContractLine", "Deadline", "Payment", "CartSession"]),
    ("\U0001F6CD Catalogo & Servizi", ["CatalogService", "ServiceCategory", "Service", "ServiceVariant", "DeadlineTemplate"]),
    ("✉ Documenti & Comunicazioni", ["Communication", "Document", "EmailTemplate", "InvoiceExport", "AuditLog"]),
    ("⚙ Configurazione", ["OrganizerSettings", "EmailSettings", "User", "Group", "LogEntry"]),
]

_orig_get_app_list = admin.AdminSite.get_app_list


def _grouped_get_app_list(self, request, app_label=None):
    # Per la pagina di una SINGOLA app (es. /admin/contracts/), standard.
    if app_label:
        return _orig_get_app_list(self, request, app_label)

    app_dict = self._build_app_dict(request)
    model_by_name = {}
    for app in app_dict.values():
        for m in app['models']:
            model_by_name[m['object_name']] = m

    result = []
    used = set()
    for idx, (group_name, names) in enumerate(GROUPS):
        models = [model_by_name[n] for n in names if n in model_by_name]
        if not models:
            continue
        used.update(n for n in names if n in model_by_name)
        result.append({
            'name': group_name,
            'app_label': 'grp_%d' % idx,
            'app_url': '',
            'has_module_perms': True,
            'models': models,
        })

    # Modelli non mappati (es. app nuove) -> sezione "Altro", per non perderli.
    leftover = [m for n, m in model_by_name.items() if n not in used]
    if leftover:
        result.append({
            'name': 'Altro', 'app_label': 'grp_altro', 'app_url': '',
            'has_module_perms': True,
            'models': sorted(leftover, key=lambda x: x['name']),
        })
    return result


def apply_admin_grouping():
    """Installa il get_app_list raggruppato sul sito admin di default."""
    admin.site.get_app_list = types.MethodType(_grouped_get_app_list, admin.site)
