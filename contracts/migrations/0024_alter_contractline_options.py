from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0023_alter_contractline_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='contractline',
            options={'ordering': ['contract', 'display_order', 'created_at', 'id'], 'verbose_name': 'Riga contratto', 'verbose_name_plural': 'Righe contratto'},
        ),
    ]
