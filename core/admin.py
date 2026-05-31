"""
Customizzazione globale dell'admin Django.

Cambia il titolo e l'header del sito admin.
"""
from django.contrib import admin

admin.site.site_header = "Sponsor Manager"
admin.site.site_title = "Sponsor Manager Admin"
admin.site.index_title = "Pannello di gestione"


from django.urls import reverse
from django.utils.html import format_html
from .models import OrganizerSettings


@admin.register(OrganizerSettings)
class OrganizerSettingsAdmin(admin.ModelAdmin):
    """Pannello unico (singleton) per i dati della segreteria."""
    fieldsets = (
        ("Anagrafica segreteria", {
            "fields": ("name", "address", "email", "phone", "website"),
        }),
        ("Dati fiscali", {
            "fields": ("vat_number", "rea"),
        }),
        ("Logo", {
            "fields": ("logo",),
        }),
    )

    def has_add_permission(self, request):
        # Niente "Aggiungi": esiste un solo record.
        return not OrganizerSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Vai dritto alla scheda unica invece della lista.
        obj = OrganizerSettings.load()
        from django.shortcuts import redirect
        url = reverse("admin:core_organizersettings_change", args=[obj.pk])
        return redirect(url)

# --- Link "Cruscotto" nel menu laterale sinistro dell'admin ---
_orig_get_app_list = admin.site.get_app_list

def _cruscotto_app_list(request, app_label=None):
    try:
        base = list(_orig_get_app_list(request, app_label))
    except TypeError:
        base = list(_orig_get_app_list(request))
    entry = {
        'name': 'Cruscotto',
        'app_label': 'cruscotto_link',
        'app_url': '/admin/cruscotto/',
        'has_module_perms': True,
        'models': [{
            'name': 'Apri Cruscotto',
            'object_name': 'Cruscotto',
            'admin_url': '/admin/cruscotto/',
            'add_url': None,
            'view_only': True,
        }],
    }
    return [entry] + base

admin.site.get_app_list = _cruscotto_app_list
