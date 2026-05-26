from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0006_contract_letter_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='deposit_percent',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Acconto %', help_text='Percentuale di acconto (es. 30 per il 30%). Vuoto = pagamento unico (tutto a saldo).'),
        ),
    ]
