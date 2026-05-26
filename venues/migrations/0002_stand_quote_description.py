from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('venues', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='stand',
            name='quote_description',
            field=models.TextField(blank=True, verbose_name='Descrizione per preventivo', help_text="Descrizione dello stand mostrata SOLO nel preventivo (es. 'stand rettangolare con 1 lato libero, senza arredo...'). Non compare nel contratto."),
        ),
        migrations.AddField(
            model_name='standblock',
            name='quote_description',
            field=models.TextField(blank=True, verbose_name='Descrizione per preventivo', help_text="Descrizione dello stand mostrata SOLO nel preventivo (es. 'stand rettangolare con 1 lato libero, senza arredo...'). Non compare nel contratto."),
        ),
    ]
