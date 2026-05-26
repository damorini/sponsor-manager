from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizersettings',
            name='payment_deposit_days_after_signing',
            field=models.IntegerField(default=0, verbose_name='Giorni scadenza acconto (dopo firma)', help_text="L'acconto scade questo numero di giorni dopo la firma del contratto."),
        ),
        migrations.AddField(
            model_name='organizersettings',
            name='payment_balance_days_before_event',
            field=models.IntegerField(default=0, verbose_name='Giorni scadenza saldo (prima evento)', help_text="Il saldo scade questo numero di giorni prima dell'inizio dell'evento."),
        ),
    ]
