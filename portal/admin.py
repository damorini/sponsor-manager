"""
Configurazione Django Admin per il portale sponsor.
"""
from django.contrib import admin
from .models import Wishlist, WishlistItem


class WishlistItemInline(admin.TabularInline):
    """Inline per visualizzare gli elementi della wishlist."""
    model = WishlistItem
    extra = 0
    fields = ('service', 'added_at')
    readonly_fields = ('added_at',)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    """Admin per la Wishlist."""
    list_display = ('user', 'get_service_count', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('user__email', 'user__username', 'services__name')
    inlines = [WishlistItemInline]
    readonly_fields = ('created_at', 'updated_at')
    
    def get_service_count(self, obj):
        """Mostra il numero di servizi nella wishlist."""
        return obj.services.count()
    get_service_count.short_description = "Numero servizi"


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    """Admin per gli elementi della wishlist."""
    list_display = ('wishlist', 'service', 'added_at')
    list_filter = ('added_at', 'wishlist__user')
    search_fields = ('wishlist__user__email', 'service__name')
    readonly_fields = ('added_at',)
