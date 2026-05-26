from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shared', '0005_documenttype_quote'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='document_type',
            field=models.CharField(
                choices=[
                    ('contract_pdf', 'Contratto PDF'),
                    ('quote', 'Preventivo'),
                    ('client_summary', 'Scheda cliente'),
                    ('signed_contract', 'Contratto firmato'),
                    ('invoice', 'Fattura'),
                    ('logo', 'Logo'),
                    ('adv_material', 'Materiale ADV'),
                    ('workshop_abstract', 'Abstract workshop'),
                    ('compliance_aifa', 'Compliance AIFA'),
                    ('stand_plan', 'Scheda stand'),
                    ('event_floorplan', 'Planimetria evento'),
                    ('other', 'Altro'),
                ],
                max_length=50,
                verbose_name='Tipo documento',
            ),
        ),
    ]
