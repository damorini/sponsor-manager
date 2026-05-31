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
