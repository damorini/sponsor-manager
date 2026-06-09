# Divide il "Nome completo" esistente in Nome (tutto tranne l'ultima parola)
# e Cognome (ultima parola), per i contatti che non hanno ancora i due campi.

from django.db import migrations


def split_names(apps, schema_editor):
    Contact = apps.get_model("sponsors", "Contact")
    for c in Contact.objects.all().iterator():
        if (c.first_name or '').strip() or (c.last_name or '').strip():
            continue
        parts = (c.full_name or '').split()
        if not parts:
            continue
        c.last_name = parts[-1]
        c.first_name = ' '.join(parts[:-1])
        c.save(update_fields=['first_name', 'last_name'])


def unsplit(apps, schema_editor):
    pass  # reversibile: i dati restano in full_name


class Migration(migrations.Migration):

    dependencies = [
        ("sponsors", "0014_contact_first_name_contact_last_name_and_more"),
    ]

    operations = [
        migrations.RunPython(split_names, unsplit),
    ]
