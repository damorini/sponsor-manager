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

    # Pagine di conferma che spiegano la regola cestino/eliminazione definitiva
    delete_confirmation_template = 'admin/softdelete_delete_confirmation.html'
    delete_selected_confirmation_template = (
        'admin/softdelete_delete_selected_confirmation.html')

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

    def get_deleted_objects(self, objs, request):
        """La pagina di conferma di Django BLOCCA l'eliminazione se altri
        oggetti la "proteggono" (FK on_delete=PROTECT), contando anche le
        righe gia' soft-cancellate e i record senza cestino come i pagamenti
        (il collector lavora a livello DB). Quando l'eliminazione e' SOFT
        quei blocchi sono fantasmi: le righe restano nel database e nessuna
        FK viene rotta.

        ATTENZIONE: vale SOLO per il soft delete. Se anche un solo oggetto e'
        gia' nel cestino l'eliminazione sara' DEFINITIVA, quindi i vincoli
        PROTECT sono reali e vanno mostrati: nasconderli farebbe fallire
        l'operazione con un errore 500 (es. contratto con pagamenti).

        Regola (solo soft): blocca chi e' (a) un oggetto col cestino e (b)
        ancora attivo — es. un carrello figlio non ancora cancellato."""
        deleted_objects, model_count, perms_needed, protected = (
            super().get_deleted_objects(objs, request))
        sara_definitiva = any(
            getattr(o, 'deleted_at', None) is not None for o in objs)
        if sara_definitiva:
            return deleted_objects, model_count, perms_needed, protected
        if protected:
            from django.contrib.admin.utils import NestedObjects
            from django.db import router
            from django.utils.text import capfirst
            collector = NestedObjects(using=router.db_for_write(self.model))
            collector.collect(list(objs))
            bloccanti = [
                o for o in collector.protected
                if hasattr(o, 'deleted_at') and o.deleted_at is None
            ]
            protected = [
                f"{capfirst(o._meta.verbose_name)}: {o}" for o in bloccanti
            ]
        return deleted_objects, model_count, perms_needed, protected

    # ---- Eliminazione: soft se attivo, DEFINITIVA se gia' nel cestino ----
    #
    # Prima, eliminare dal cestino rifaceva un soft delete su un record gia'
    # cancellato: Django confermava "eliminato" ma la riga restava li'. Ora
    # il cestino si comporta come ci si aspetta: la seconda eliminazione e'
    # quella definitiva.

    @staticmethod
    def _elimina_definitivamente(obj):
        """Hard delete del record + documenti/comunicazioni collegati via
        GenericForeignKey (che il cascade del DB non tocca, e resterebbero
        orfani e invisibili nel database)."""
        from django.contrib.contenttypes.models import ContentType
        try:
            from shared.models import Communication, Document
            ct = ContentType.objects.get_for_model(obj.__class__)
            Document.all_objects.filter(content_type=ct, object_id=obj.pk).delete()
            Communication.objects.filter(content_type=ct, object_id=obj.pk).delete()
        except Exception:
            pass  # la cancellazione del record resta comunque prioritaria
        obj.delete(hard=True)

    @staticmethod
    def _motivo_protezione(err):
        """Traduce il ProtectedError del DB in una frase comprensibile."""
        nomi = set()
        for o in getattr(err, 'protected_objects', []) or []:
            nomi.add(o._meta.verbose_name)
        return ", ".join(sorted(nomi)) or "altri record collegati"

    def delete_queryset(self, request, queryset):
        """Soft delete in blocco; per i record GIA' nel cestino, definitivo."""
        from django.db.models import ProtectedError
        n_cestino, n_definitivi, bloccati = 0, 0, []
        for obj in queryset:
            if getattr(obj, 'deleted_at', None) is not None:
                try:
                    self._elimina_definitivamente(obj)
                    n_definitivi += 1
                except ProtectedError as e:
                    bloccati.append(f"{obj} (collegato a: {self._motivo_protezione(e)})")
            else:
                obj.delete()  # soft (override del modello)
                n_cestino += 1
        if n_cestino:
            self.message_user(
                request,
                f"{n_cestino} elemento/i spostato/i nel cestino "
                "(recuperabili dal filtro 'Nel cestino').")
        if n_definitivi:
            self.message_user(
                request,
                f"{n_definitivi} elemento/i erano già nel cestino: eliminati "
                "DEFINITIVAMENTE dal database (operazione non reversibile).")
        if bloccati:
            self.message_user(
                request,
                "NON eliminati (restano nel cestino) perché il database li "
                "protegge: " + " | ".join(bloccati)
                + ". Per eliminarli davvero bisogna prima rimuovere i record "
                  "collegati (es. gli incassi registrati).",
                level='WARNING')

    def delete_model(self, request, obj):
        """Eliminazione dal singolo record: stessa regola del blocco."""
        from django.db.models import ProtectedError
        if getattr(obj, 'deleted_at', None) is not None:
            try:
                self._elimina_definitivamente(obj)
            except ProtectedError as e:
                self.message_user(
                    request,
                    "NON eliminato (resta nel cestino): il database lo protegge "
                    f"perché è collegato a {self._motivo_protezione(e)}. "
                    "Per eliminarlo davvero bisogna prima rimuovere quei record "
                    "(es. gli incassi registrati).",
                    level='WARNING')
                return
            self.message_user(
                request,
                "Era già nel cestino: eliminato DEFINITIVAMENTE dal database "
                "(operazione non reversibile).")
        else:
            obj.delete()
            self.message_user(
                request,
                "Spostato nel cestino (recuperabile dal filtro 'Nel cestino').")

    @admin.action(description="Ripristina dal cestino")
    def action_restore(self, request, queryset):
        n = 0
        for obj in queryset:
            if getattr(obj, 'deleted_at', None) is not None:
                obj.restore()
                n += 1
        self.message_user(request, f"{n} elemento/i ripristinato/i.")
