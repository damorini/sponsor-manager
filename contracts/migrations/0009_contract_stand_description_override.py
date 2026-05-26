from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0008_contract_payment_due_overrides'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='stand_description_override',
            field=models.TextField(blank=True, verbose_name='Descrizione stand (preventivo, manuale)', help_text='Se compilata, sostituisce la descrizione dello stand nel preventivo di questo contratto. Vuota = usa la descrizione dello stand/blocco.'),
        ),
    ]
