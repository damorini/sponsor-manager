# -*- coding: utf-8 -*-
# Migrazione NON distruttiva: introduce il modello intermedio ServiceInclusion
# per la quantita' dei servizi inclusi, preservando i collegamenti esistenti.
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def copia_inclusioni(apps, schema_editor):
    """Copia i collegamenti del vecchio M2M auto-generato nel nuovo modello
    intermedio, impostando quantita' = 1 (comportamento pre-esistente)."""
    Service = apps.get_model('catalog', 'Service')
    ServiceInclusion = apps.get_model('catalog', 'ServiceInclusion')
    for parent in Service.objects.all():
        try:
            figli = list(parent.included_services.all())
        except Exception:
            figli = []
        for child in figli:
            ServiceInclusion.objects.get_or_create(
                parent=parent, child=child, defaults={'quantity': 1}
            )


def reverse_noop(apps, schema_editor):
    # In reverse i dati restano nel through finche' non viene rimosso da AddField inverso.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_catalogservicevariant_label_en_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceInclusion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1, help_text='Quante unita\' di questo accessorio vengono incluse.', validators=[django.core.validators.MinValueValidator(1)], verbose_name="Quantita' inclusa")),
                ('child', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inclusion_links', to='catalog.service', verbose_name='Servizio incluso')),
                ('parent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inclusions', to='catalog.service', verbose_name='Servizio principale')),
            ],
            options={
                'verbose_name': 'Servizio incluso',
                'verbose_name_plural': 'Servizi inclusi',
            },
        ),
        migrations.AddConstraint(
            model_name='serviceinclusion',
            constraint=models.UniqueConstraint(fields=('parent', 'child'), name='serviceinclusion_unique_parent_child'),
        ),
        # 1) copia i dati esistenti PRIMA di smontare il vecchio M2M
        migrations.RunPython(copia_inclusioni, reverse_noop),
        # 2) smonta il vecchio M2M auto-generato (rimuove la tabella di join implicita)
        migrations.RemoveField(
            model_name='service',
            name='included_services',
        ),
        # 3) rimette il M2M usando il through esplicito (a DB non crea tabelle)
        migrations.AddField(
            model_name='service',
            name='included_services',
            field=models.ManyToManyField(blank=True, help_text="Servizi aggiunti automaticamente a \u20ac 0 quando questo servizio viene venduto. Le loro scadenze materiali si generano alla firma. La quantita' inclusa si imposta nella sezione 'Servizi inclusi' in fondo a questa pagina.", related_name='included_in', through='catalog.ServiceInclusion', through_fields=('parent', 'child'), to='catalog.service', verbose_name='Servizi inclusi (accessori)'),
        ),
    ]
