from django.db import migrations, models


def numera_inclusi(apps, schema_editor):
    # gli inclusi esistenti tengono l'ordine di oggi (quello di inserimento)
    ServiceInclusion = apps.get_model('catalog', 'ServiceInclusion')
    pos, padre = 0, None
    for inc in ServiceInclusion.objects.order_by('parent_id', 'id'):
        if inc.parent_id != padre:
            pos, padre = 0, inc.parent_id
        pos += 1
        ServiceInclusion.objects.filter(pk=inc.pk).update(display_order=pos)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0015_deadlinetemplate_max_file_size_mb'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceinclusion',
            name='display_order',
            field=models.PositiveIntegerField(default=0, help_text="Posizione nel preventivo: prima i numeri piu' bassi. 0 = in fondo alla lista.", verbose_name='Ordine'),
        ),
        migrations.AlterModelOptions(
            name='serviceinclusion',
            options={'ordering': ['display_order', 'id'], 'verbose_name': 'Servizio incluso', 'verbose_name_plural': 'Servizi inclusi'},
        ),
        migrations.RunPython(numera_inclusi, migrations.RunPython.noop),
    ]
