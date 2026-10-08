"""Riga del blocco di stand: indica gli stand della planimetria che lo
compongono e le loro voci incluse, ognuna una volta sola."""
from datetime import date
from decimal import Decimal

from contracts.models import Contract, ContractKind, ContractStatus
from contracts.services.stand_line import genera_riga_da_stand
from events.models import Event
from venues.models import Stand, StandBlock


def _contratto(sponsor, lingua='it', descrizione_blocco=None):
    ev = Event.objects.create(name={'it': 'Ev Blocco'}, code='BRG',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    b = StandBlock.objects.create(event=ev, code='SELTEC',
                                  quote_description=descrizione_blocco or {})
    Stand.objects.create(event=ev, code='29-A', base_price=Decimal('29000'), stand_block=b,
                         quote_description={'it': '· Area Nuda \n· Live on stage \n· Pagina ADV'})
    Stand.objects.create(event=ev, code='30-A', base_price=Decimal('29000'), stand_block=b,
                         quote_description={'it': '· Area nuda· Pagina ADV · Appendimento'})
    return Contract.objects.create(sponsor=sponsor, event=ev, stand_block=b,
                                   contract_kind=ContractKind.MAIN,
                                   status=ContractStatus.DRAFT, language=lingua)


def _riga(c):
    if not c.lines.filter(notes__contains='block:SELTEC').exists():
        assert genera_riga_da_stand(c)[0] == 'creata'
    return c.lines.get(notes__contains='block:SELTEC')


def test_nome_e_voci_del_blocco(sponsor):
    contratto = _contratto(sponsor)
    riga = _riga(contratto)
    assert riga.service_name_snapshot == (
        'Spazio espositivo - Blocco SELTEC corrispondente agli stand n° 29-A e 30-A '
        'della planimetria ufficiale')
    assert riga.service_description_snapshot.splitlines() == [
        '· Area Nuda', '· Live on stage', '· Pagina ADV', '· Appendimento']


def test_descrizione_del_blocco_prevale(sponsor):
    riga = _riga(_contratto(sponsor, descrizione_blocco={'it': 'Isola centrale'}))
    assert riga.service_description_snapshot == 'Isola centrale'


def test_in_inglese(sponsor):
    riga = _riga(_contratto(sponsor, lingua='en'))
    assert riga.service_name_snapshot == (
        'Exhibition space - Block SELTEC, corresponding to stands no. 29-A and 30-A '
        'of the official floor plan')


def _pacchetto(ev, tipologia, inclusi):
    from catalog.models import Service, ServiceInclusion
    from contracts.services.stand_line import get_or_create_stand_service
    pac = get_or_create_stand_service(ev, tipologia)
    for codice, qta in inclusi:
        figlio = Service.objects.filter(event=ev, code=codice).first() or \
            Service.objects.create(event=ev, code=codice, name={'it': codice.title()},
                                   base_price=Decimal('50'))
        ServiceInclusion.objects.create(parent=pac, child=figlio, quantity=qta)
    return pac


def _blocco_misto(sponsor):
    ev = Event.objects.create(name={'it': 'Ev Misto'}, code='MIX',
                              start_date=date(2027, 2, 25), end_date=date(2027, 2, 27))
    _pacchetto(ev, 'Main', [('ISCRIZIONI', 3), ('BADGE', 2)])
    _pacchetto(ev, 'Regular', [('BADGE', 1), ('DESK', 1)])
    b = StandBlock.objects.create(event=ev, code='MIX')
    Stand.objects.create(event=ev, code='1', stand_type='Main', base_price=Decimal('30000'),
                         stand_block=b, quote_description={'it': '· Area nuda· Pagina ADV'})
    Stand.objects.create(event=ev, code='2', stand_type='Main', base_price=Decimal('30000'),
                         stand_block=b, quote_description={'it': '· Area nuda· Pagina ADV'})
    Stand.objects.create(event=ev, code='3', stand_type='Regular', base_price=Decimal('9000'),
                         stand_block=b, quote_description={'it': '· Desk· Sedie'})
    return Contract.objects.create(sponsor=sponsor, event=ev, stand_block=b,
                                   contract_kind=ContractKind.MAIN,
                                   status=ContractStatus.DRAFT, language='it')


def test_inclusi_sommati_voci_dello_stand_superiore(sponsor):
    c = _blocco_misto(sponsor)
    if not c.lines.filter(notes__contains='block:MIX').exists():
        genera_riga_da_stand(c)
    riga = c.lines.get(notes__contains='block:MIX')
    assert riga.service.code == 'SPAZIO_ESPOSITIVO_MAIN'          # tipologia superiore
    assert riga.service_description_snapshot.splitlines() == ['· Area nuda', '· Pagina ADV']
    qta = {l.service.code: l.quantity for l in c.lines.all() if l.is_included}
    assert qta == {'ISCRIZIONI': 6, 'BADGE': 5, 'DESK': 1}          # 3+3; 2+2+1; 1
    assert all(l.unit_price == 0 for l in c.lines.all() if l.is_included)
    assert c.lines.count() == 4                                      # niente doppioni
