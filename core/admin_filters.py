"""Filtro admin riutilizzabile: 'Per evento' a menu a tendina."""
from django.contrib import admin


def evento_filter(field_path='event'):
    """Ritorna una classe SimpleListFilter che filtra per evento tramite field_path
    (es. 'event', 'contract__event', 'service__event')."""

    class _EventoFilter(admin.SimpleListFilter):
        title = "Evento"
        parameter_name = "evento"
        template = "admin/evento_dropdown_filter.html"

        def lookups(self, request, model_admin):
            from events.models import Event
            return [(str(e.pk), str(e)) for e in Event.objects.all().order_by("-created_at")]

        def queryset(self, request, queryset):
            v = self.value()
            if v:
                return queryset.filter(**{field_path + "_id": v})
            return queryset

    return _EventoFilter


def nascondi_archiviati_filter(field_path='event'):
    """SimpleListFilter che NASCONDE di default gli elementi di eventi archiviati.
    L'operatore può scegliere di includerli o vederli da soli. field_path è il
    percorso verso l'evento (es. 'event', 'service__event')."""

    class _ArchiviatiFilter(admin.SimpleListFilter):
        title = "Eventi archiviati"
        parameter_name = "arch"

        def lookups(self, request, model_admin):
            return [('incl', 'Includi archiviati'), ('solo', 'Solo archiviati')]

        def choices(self, changelist):
            # Rinomina la prima opzione (il default "Tutti") in chiaro.
            opts = list(super().choices(changelist))
            if opts:
                opts[0]['display'] = 'Attivi (nascondi archiviati)'
            for choice in opts:
                yield choice

        def queryset(self, request, queryset):
            from events.models import EventStatus
            key = f"{field_path}__status"
            v = self.value()
            if v == 'solo':
                return queryset.filter(**{key: EventStatus.ARCHIVED})
            if v == 'incl':
                return queryset
            return queryset.exclude(**{key: EventStatus.ARCHIVED})

    return _ArchiviatiFilter
