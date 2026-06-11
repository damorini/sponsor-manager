"""
Guardia anti-hard-delete nell'admin: l'azione standard 'delete_selected' fa
queryset.delete() (bulk SQL) che BYPASSA il soft-delete del modello e cancella
DEFINITIVAMENTE. Il SoftDeleteAdminMixin la trasforma in soft delete + aggiunge
ripristino e filtro 'cestino'.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.contrib import admin as djadmin
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage

from core.softdelete_admin import SoftDeleteAdminMixin, DeletedListFilter


class _ContractAdminT(SoftDeleteAdminMixin, djadmin.ModelAdmin):
    pass


def _req():
    r = RequestFactory().post('/')
    setattr(r, 'session', {})
    setattr(r, '_messages', FallbackStorage(r))
    return r


def _contract(sponsor, num):
    from events.models import Event
    from contracts.models import Contract, ContractKind, ContractStatus
    ev, _ = Event.objects.get_or_create(
        code='DEL', defaults=dict(name={'it': 'Del', 'en': 'Del'},
                                  start_date=date(2026, 11, 1), end_date=date(2026, 11, 2)))
    return Contract.objects.create(
        sponsor=sponsor, event=ev, contract_kind=ContractKind.MAIN,
        status=ContractStatus.SIGNED, contract_number=num, total=Decimal('100.00'))


@pytest.mark.django_db
def test_delete_queryset_is_soft_not_hard(sponsor):
    from contracts.models import Contract
    c = _contract(sponsor, 'DEL-26-001')
    admin_obj = _ContractAdminT(Contract, djadmin.site)

    admin_obj.delete_queryset(_req(), Contract.objects.all())

    # NON cancellato fisicamente: ancora in all_objects, ma con deleted_at
    assert Contract.objects.filter(pk=c.pk).count() == 0           # nascosto
    assert Contract.all_objects.filter(pk=c.pk, deleted_at__isnull=False).count() == 1


@pytest.mark.django_db
def test_action_restore_brings_back(sponsor):
    from contracts.models import Contract
    c = _contract(sponsor, 'DEL-26-002')
    c.delete()  # soft
    assert Contract.objects.filter(pk=c.pk).count() == 0
    admin_obj = _ContractAdminT(Contract, djadmin.site)

    admin_obj.action_restore(_req(), Contract.all_objects.all())

    assert Contract.objects.filter(pk=c.pk).count() == 1


@pytest.mark.django_db
def test_deleted_filter_default_alive_and_cestino_dead(sponsor):
    from contracts.models import Contract
    alive = _contract(sponsor, 'DEL-26-003')
    dead = _contract(sponsor, 'DEL-26-004')
    dead.delete()  # soft

    def _filter(value):
        f = DeletedListFilter.__new__(DeletedListFilter)
        f.used_parameters = {} if value is None else {'trash': value}
        return f

    res_default = _filter(None).queryset(_req(), Contract.all_objects.all())
    ids_default = set(res_default.values_list('pk', flat=True))
    assert alive.pk in ids_default and dead.pk not in ids_default

    res_trash = _filter('cestino').queryset(_req(), Contract.all_objects.all())
    ids_trash = set(res_trash.values_list('pk', flat=True))
    assert dead.pk in ids_trash and alive.pk not in ids_trash
