"""
Migra i vecchi 'portal_message' (singolo banner sullo Sponsor) nel nuovo
archivio messaggi (PortalMessage), come messaggi NON letti. Poi svuota il
vecchio campo per non mostrarli due volte.
"""
from django.db import migrations


def migra_avanti(apps, schema_editor):
    Sponsor = apps.get_model('sponsors', 'Sponsor')
    PortalMessage = apps.get_model('sponsors', 'PortalMessage')
    for sp in Sponsor.objects.exclude(portal_message='').exclude(portal_message=None):
        testo = (sp.portal_message or '').strip()
        if not testo:
            continue
        PortalMessage.objects.create(sponsor=sp, body=testo, is_active=True)
        sp.portal_message = ''
        sp.save(update_fields=['portal_message'])


def migra_indietro(apps, schema_editor):
    # Non ripristiniamo: i messaggi restano nell'archivio.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('sponsors', '0009_portalmessage'),
    ]
    operations = [
        migrations.RunPython(migra_avanti, migra_indietro),
    ]
