"""
Admin helper per i modelli SoftDeleteModel (Sponsor, Contract).

Problema risolto: l'azione admin standard 'delete_selected' chiama
queryset.delete() (bulk SQL) che BYPASSA l'override soft-delete del modello e
cancella DEFINITIVAMENTE (con cascade su righe/scadenze/documenti). Questo mixin
la rende soft, espone un 'Cestino' (filtro) e un'azione di ripristino.
"""
from django.contrib import admin


class DeletedListFilter(admin.SimpleListFilter):
    """Mostra Attivi (default), Nel cestino, o Tutti."""
    title = "Stato record"
    parameter_name = "trash"

    def lookups(self, request, model_admin):
        return (('cestino', 'Nel cestino'), ('tutti', 'Tutti'))

    def queryset(self, request, queryset):
        val = self.value()
        if val == 'cestino':
            return queryset.filter(deleted_at__isnull=False)
        if val == 'tutti':
            return queryset
        return queryset.filter(deleted_at__isnull=True)  # default: attivi

    def choices(self, changelist):
        # Rinomina l'opzione di default ('All') in 'Attivi'.
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': 'Attivi',
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': str(self.value()) == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }


class SoftDeleteAdminMixin:
    """Da anteporre a ModelAdmin per i SoftDeleteModel.

    - delete in blocco => soft (non bypassa piu' il modello);
    - get_queryset parte dagli attivi e include i cancellati SOLO col filtro
      'cestino'/'tutti' attivo (autocomplete e liste restano puliti);
    - azione 'Ripristina dal cestino'.
    Ricorda di aggiungere DeletedListFilter a list_filter e 'action_restore' ad actions.
    """

    def get_queryset(self, request):
        trash = request.GET.get('trash')
        if trash in ('cestino', 'tutti'):
            manager = self.model.all_objects
        else:
            manager = self.model._default_manager
        qs = manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs

    def delete_queryset(self, request, queryset):
        """Soft delete in blocco (l'azione standard farebbe hard delete)."""
        n = 0
        for obj in queryset:
            obj.delete()  # soft (override del modello)
            n += 1
        self.message_user(
            request,
            f"{n} elemento/i spostato/i nel cestino (recuperabili dal filtro 'Nel cestino').")

    @admin.action(description="Ripristina dal cestino")
    def action_restore(self, request, queryset):
        n = 0
        for obj in queryset:
            if getattr(obj, 'deleted_at', None) is not None:
                obj.restore()
                n += 1
        self.message_user(request, f"{n} elemento/i ripristinato/i.")
