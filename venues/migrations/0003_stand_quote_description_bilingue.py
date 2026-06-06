"""
Rende bilingue (IT/EN) la 'quote_description' di Stand e StandBlock:
da TextField a JSONField {"it": ..., "en": ...}.

Approccio sicuro (niente cast text->jsonb): aggiunge un campo JSON temporaneo,
copia il testo esistente in {"it": testo}, rimuove il vecchio campo e rinomina
il temporaneo. I dati esistenti vengono preservati nella chiave 'it'.
"""
from django.db import migrations, models


HELP = ("Descrizione mostrata SOLO nel preventivo "
        "(es. 'stand rettangolare con 1 lato libero, senza arredo...'). "
        "Non compare nel contratto. L'inglese si compila da solo al salvataggio.")


def copy_forward(apps, schema_editor):
    for name in ('Stand', 'StandBlock'):
        M = apps.get_model('venues', name)
        for obj in M.objects.all():
            txt = obj.quote_description
            txt = txt.strip() if isinstance(txt, str) else ''
            obj.quote_description_i18n = {'it': txt} if txt else {}
            obj.save(update_fields=['quote_description_i18n'])


def copy_backward(apps, schema_editor):
    for name in ('Stand', 'StandBlock'):
        M = apps.get_model('venues', name)
        for obj in M.objects.all():
            val = obj.quote_description_i18n or {}
            obj.quote_description = (val.get('it', '') if isinstance(val, dict) else '') or ''
            obj.save(update_fields=['quote_description'])


class Migration(migrations.Migration):

    dependencies = [
        ('venues', '0002_stand_quote_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='stand',
            name='quote_description_i18n',
            field=models.JSONField(default=dict, blank=True,
                                   verbose_name='Descrizione per preventivo (IT/EN)', help_text=HELP),
        ),
        migrations.AddField(
            model_name='standblock',
            name='quote_description_i18n',
            field=models.JSONField(default=dict, blank=True,
                                   verbose_name='Descrizione per preventivo (IT/EN)', help_text=HELP),
        ),
        migrations.RunPython(copy_forward, copy_backward),
        migrations.RemoveField(model_name='stand', name='quote_description'),
        migrations.RemoveField(model_name='standblock', name='quote_description'),
        migrations.RenameField(model_name='stand', old_name='quote_description_i18n', new_name='quote_description'),
        migrations.RenameField(model_name='standblock', old_name='quote_description_i18n', new_name='quote_description'),
    ]
