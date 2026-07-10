"""
Configurazione Django Admin per il portale sponsor.

La wishlist è scelta dal CLIENTE: in admin è di SOLA LETTURA (l'operatore
la consulta, non la modifica).
"""
from django.contrib import admin
from .models import Wishlist, WishlistItem


class WishlistItemInline(admin.TabularInline):
    """Articoli scelti dal cliente: sola lettura (niente tendina, niente aggiunta)."""
    model = WishlistItem
    extra = 0
    fields = ('service', 'added_at')
    readonly_fields = ('service', 'added_at')
    can_delete = False
    verbose_name = "Articolo scelto dal cliente"
    verbose_name_plural = "Articoli scelti dal cliente (sola lettura)"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin per la Wishlist (consultazione)."""
    list_display = ('user', 'get_service_count', 'created_at', 'updated_at',
                    'last_reminder_sent_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__email', 'user__username', 'services__name')
    inlines = [WishlistItemInline]
    readonly_fields = ('user', 'created_at', 'updated_at', 'last_reminder_sent_at')

    def has_add_permission(self, request):
        # Le wishlist le crea il cliente dal portale, non l'operatore.
        return False

    @admin.display(description="Numero servizi")
    def get_service_count(self, obj):
        return obj.services.count()


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    """Elementi wishlist: sola lettura (ricerca/consultazione)."""

    def get_queryset(self, request):
        from core.event_scope import scope_lista_evento_attivo
        return scope_lista_evento_attivo(
            request, super().get_queryset(request), 'service__event')

    list_display = ('wishlist', 'service', 'added_at')
    list_filter = ('added_at', 'wishlist__user')
    search_fields = ('wishlist__user__email', 'service__name')
    readonly_fields = ('wishlist', 'service', 'added_at')

    def has_add_permission(self, request):
        return False
