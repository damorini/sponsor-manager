"""
End-to-end del comando importa_catalogo (refactor catalogo giugno).

Importa CatalogService + ServiceCategory dal file Excel `template_catalogo.xlsx`
(committato a repo root). Richiede openpyxl.
"""
import pytest
from io import StringIO
from django.core.management import call_command

from catalog.models import CatalogService, ServiceCategory


@pytest.mark.django_db
def test_importa_catalogo_creates_records():
    """Su DB vuoto importa i 3 servizi del template."""
    out = StringIO()
    call_command('importa_catalogo', file='template_catalogo.xlsx', stdout=out)

    assert CatalogService.objects.count() == 3
    codes = set(CatalogService.objects.values_list('code', flat=True))
    assert codes == {'SEDIA_IMBOTTITA', 'MULETTO', 'WORKSHOP_30'}
    assert ServiceCategory.objects.exists()


@pytest.mark.django_db
def test_importa_catalogo_dry_run_saves_nothing():
    """--dry-run non scrive nulla nel DB."""
    out = StringIO()
    call_command('importa_catalogo', file='template_catalogo.xlsx',
                 dry_run=True, stdout=out)
    assert CatalogService.objects.count() == 0
