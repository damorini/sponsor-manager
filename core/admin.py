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
