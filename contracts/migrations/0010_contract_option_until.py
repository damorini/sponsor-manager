from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0009_contract_stand_description_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='option_until',
            field=models.DateField(blank=True, null=True, verbose_name='Spazio opzionato fino al', help_text='Se valorizzata e non scaduta, lo spazio (stand/blocco) risulta opzionato (riservato) per questo cliente anche in bozza, e non e proponibile ad altri. Alla scadenza lo spazio torna disponibile.'),
        ),
    ]
