"""Gli "a capo" dentro le celle Excel arrivano come "_x000D_": gli import li
devono riconvertire, non copiarli nelle descrizioni."""
from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from openpyxl import Workbook


@pytest.mark.django_db
def test_importa_servizi_converte_a_capo_excel(tmp_path):
    from catalog.models import Service
    from events.models import Event

    ev = Event.objects.create(name={'it': 'Ev'}, code='XLS', slug='ev-xls',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    wb = Workbook()
    ws = wb.active
    ws.append(['evento_slug', 'code', 'nome_it', 'descrizione_it', 'descrizione_en', 'prezzo_base'])
    ws.append([ev.slug, 'ADESIVO', 'Adesivo',
               'Adesivo su vetrata._x000D_\nStampa a nostro carico._x000D_',
               'Window sticker._x000D_\nPrinted by us.', 100])
    file = tmp_path / 'servizi.xlsx'
    wb.save(file)

    call_command('importa_servizi', file=str(file), stdout=StringIO())

    s = Service.objects.get(event=ev, code='ADESIVO')
    assert s.description['it'] == 'Adesivo su vetrata.\nStampa a nostro carico.'
    assert s.description['en'] == 'Window sticker.\nPrinted by us.'


def test_righe_excel_lascia_stare_i_non_testi():
    from core.excel import righe_excel

    class Foglio:
        def iter_rows(self, values_only):
            return [('a_x000D_\nb', 3, None, 'c\r\nd')]

    assert righe_excel(Foglio()) == [('a\nb', 3, None, 'c\nd')]
