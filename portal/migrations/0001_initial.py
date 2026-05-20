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
