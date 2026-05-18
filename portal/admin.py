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
    readonly_fields = ('added_at
mkdir -p portal/migrations
cat > portal/migrations/0001_wishlist.py << 'EOF'
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Wishlist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(help_text='Un utente = una wishlist', on_delete=django.db.models.deletion.CASCADE, related_name='wishlist_obj', to=settings.AUTH_USER_MODEL, verbose_name='Utente sponsor')),
            ],
            options={
                'verbose_name': 'Wishlist',
                'verbose_name_plural': 'Wishlists',
            },
        ),
        migrations.CreateModel(
            name='WishlistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('service', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wishlist_items', to='catalog.service')),
                ('wishlist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='portal.wishlist')),
            ],
            options={
                'verbose_name': 'Elemento wishlist',
                'verbose_name_plural': 'Elementi wishlist',
                'ordering': ['-added_at'],
                'unique_together': {('wishlist', 'service')},
            },
        ),
        migrations.AddField(
            model_name='wishlist',
            name='services',
            field=models.ManyToManyField(blank=True, related_name='in_wishlists', through='portal.WishlistItem', to='catalog.Service', verbose_name='Servizi'),
        ),
    ]
