"""
Reminder email wishlist: promemoria al cliente con articoli salvati,
con avviso extra se ci sono articoli a disponibilità limitata.
"""
import pytest
from datetime import date
from decimal import Decimal

from events.models import Event
from catalog.models import Service
from portal.models import Wishlist, WishlistItem


def _service(code, total=None):
    ev = Event.objects.create(
        name={'it': 'E', 'en': 'E'}, code=code,
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 2))
    return Service.objects.create(
        event=ev, code=code, name={'it': 'Srv', 'en': 'Srv'},
        base_price=Decimal('10.00'), vat_rate=Decimal('22.00'),
        total_available=total)


@pytest.mark.django_db
def test_reminder_inviato_con_articoli(user_sponsor, mailoutbox):
    from contracts.tasks.notifications import send_wishlist_reminder
    wl = Wishlist.objects.create(user=user_sponsor)
    WishlistItem.objects.create(wishlist=wl, service=_service('WL1'))
    send_wishlist_reminder(wl.id)
    assert len(mailoutbox) == 1
    assert user_sponsor.email in mailoutbox[0].to
    wl.refresh_from_db()
    assert wl.last_reminder_sent_at is not None


@pytest.mark.django_db
def test_reminder_urgenza_se_scorte_limitate(user_sponsor, mailoutbox):
    from contracts.tasks.notifications import send_wishlist_reminder
    wl = Wishlist.objects.create(user=user_sponsor)
    WishlistItem.objects.create(wishlist=wl, service=_service('WL2', total=3))
    send_wishlist_reminder(wl.id)
    assert "DISPONIBILITA" in mailoutbox[0].body.upper()


@pytest.mark.django_db
def test_nessun_reminder_se_wishlist_vuota(user_sponsor, mailoutbox):
    from contracts.tasks.notifications import send_wishlist_reminder
    wl = Wishlist.objects.create(user=user_sponsor)
    send_wishlist_reminder(wl.id)
    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_scheduler_seleziona_wishlist(user_sponsor, mailoutbox):
    from contracts.tasks.scheduled import check_wishlist_reminders
    wl = Wishlist.objects.create(user=user_sponsor)
    WishlistItem.objects.create(wishlist=wl, service=_service('WL3'))
    n = check_wishlist_reminders()
    assert n >= 1
    assert len(mailoutbox) >= 1
