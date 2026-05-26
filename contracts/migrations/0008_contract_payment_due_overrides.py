from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0007_contract_deposit_percent'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='deposit_due_date_override',
            field=models.DateField(blank=True, null=True, verbose_name='Scadenza acconto (manuale)', help_text='Se vuoto, calcolata come data firma + giorni impostati nelle Impostazioni segreteria.'),
        ),
        migrations.AddField(
            model_name='contract',
            name='balance_due_date_override',
            field=models.DateField(blank=True, null=True, verbose_name='Scadenza saldo (manuale)', help_text='Se vuoto, calcolata come inizio evento - giorni impostati nelle Impostazioni segreteria.'),
        ),
    ]
