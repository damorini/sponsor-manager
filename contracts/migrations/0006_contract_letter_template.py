from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('shared', '0004_lettertemplate'),
        ('contracts', '0005_contract_quote_intro_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='letter_template',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='contracts',
                to='shared.lettertemplate',
                verbose_name='Template lettera preventivo',
                help_text='Template usato per generare la lettera di preventivo (al volo). '
                          'I segnaposti vengono compilati con i dati di questo contratto.',
            ),
        ),
    ]
