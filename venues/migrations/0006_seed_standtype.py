"""
Pre-carica la lista gestita StandType con le tipologie di stand GIA' usate
(valori distinti non vuoti di Stand.stand_type), così il menu a tendina parte
già popolato e nulla di esistente sparisce. Idempotente.
"""
from django.db import migrations


def seed_stand_types(apps, schema_editor):
    Stand = apps.get_model('venues', 'Stand')
    StandType = apps.get_model('venues', 'StandType')
    valori = (Stand.objects.exclude(stand_type='')
              .order_by('stand_type')
              .values_list('stand_type', flat=True)
              .distinct())
    for i, v in enumerate(dict.fromkeys(valori)):
        StandType.objects.get_or_create(name=v, defaults={'display_order': i})


class Migration(migrations.Migration):

    dependencies = [
        ('venues', '0005_standtype'),
    ]

    operations = [
        migrations.RunPython(seed_stand_types, migrations.RunPython.noop),
    ]
