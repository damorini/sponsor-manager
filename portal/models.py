"""
Modelli del portale sponsor.
"""
from django.db import models
from django.contrib.auth import get_user_model
from catalog.models import Service

User = get_user_model()


class Wishlist(models.Model):
    """Wishlist: servizi salvati da uno sponsor."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wishlist_obj',
        verbose_name="Utente sponsor",
    )
    services = models.ManyToManyField(
        Service,
        through='WishlistItem',
        related_name='in_wishlists',
        verbose_name="Servizi",
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_reminder_sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Ultimo reminder inviato il")

    class Meta:
        verbose_name = "Wishlist"
        verbose_name_plural = "Wishlists"
    
    def __str__(self):
        return f"Wishlist di {self.user.email}"
    
    def add_service(self, service):
        """Aggiungi un servizio alla wishlist."""
        WishlistItem.objects.get_or_create(wishlist=self, service=service)
    
    def remove_service(self, service):
        """Rimuovi un servizio dalla wishlist."""
        WishlistItem.objects.filter(wishlist=self, service=service).delete()
    
    def has_service(self, service):
        """Controlla se un servizio è nella wishlist."""
        return self.services.filter(id=service.id).exists()


class WishlistItem(models.Model):
    """Elemento singolo della wishlist."""
    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name='items'
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='wishlist_items'
    )
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('wishlist', 'service')
        verbose_name = "Elemento wishlist"
        verbose_name_plural = "Elementi wishlist"
        ordering = ['-added_at']
    
    def __str__(self):
        try:
            nome = self.service.translated('name', 'it')
        except Exception:
            nome = str(self.service)
        return f"{nome} · {self.wishlist.user.email}"
