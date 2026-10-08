"""Lista contratti: azione «INVIA PASS ALLESTIMENTO», colonna e filtro per
vedere a colpo d'occhio chi l'ha gia' ricevuto, anteprima della email."""
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class PassAllestimentoFilter(admin.SimpleListFilter):
    title = 'PASS allestimento'
    parameter_name = 'pass_allestimento'

    def lookups(self, request, model_admin):
        return (('no', 'Non ancora inviato'), ('si', 'Inviato'))

    def queryset(self, request, queryset):
        if self.value() == 'si':
            return queryset.filter(pass_allestimento_inviato_il__isnull=False)
        if self.value() == 'no':
            return queryset.filter(pass_allestimento_inviato_il__isnull=True)
        return queryset


class PassAllestimentoAdminMixin:

    @admin.display(description='PASS allestimento', ordering='pass_allestimento_inviato_il')
    def pass_col(self, obj):
        quando = obj.pass_allestimento_inviato_il
        if not quando:
            return mark_safe('<span style="color:#9ca3af;">—</span>')
        return format_html(
            '<span style="background:#dcfce7; color:#166534; padding:2px 8px; '
            'border-radius:10px; white-space:nowrap;" title="Inviato il {}">&#10004; {}</span>',
            timezone.localtime(quando).strftime('%d/%m/%Y %H:%M'),
            timezone.localtime(quando).strftime('%d/%m/%Y'))

    @admin.action(description='INVIA PASS ALLESTIMENTO')
    def action_invia_pass_allestimento(self, request, queryset):
        from contracts.models import ContractStatus
        from contracts.services import pass_allestimento as pa

        queryset = queryset.select_related('sponsor', 'event', 'stand', 'stand_block')
        if '_pass_confermato' not in request.POST:
            righe = []
            for c in queryset:
                dest = pa.destinatario(c)
                avvisi = []
                if c.status == ContractStatus.CANCELLED:
                    avvisi.append('contratto annullato: NON verrà inviato')
                elif c.status not in (ContractStatus.SIGNED, ContractStatus.ACTIVE,
                                      ContractStatus.COMPLETED):
                    avvisi.append(f'contratto «{c.get_status_display()}», non ancora firmato')
                if dest is None:
                    avvisi.append('nessun indirizzo email: NON verrà inviato')
                if not c.stand_id and not c.stand_block_id:
                    avvisi.append('nessuno stand assegnato')
                righe.append({
                    'c': c, 'email': getattr(dest, 'email', ''), 'avvisi': avvisi,
                    'anteprima': reverse('admin:contracts_contract_anteprima_pass', args=[c.pk]),
                })
            eventi = {c.event_id: c.event for c in queryset}
            mancano = [ev.name for ev in eventi.values() if not ev.setup_days.exists()
                       or not (ev.magazzino_indirizzo or '').strip()]
            return render(request, 'admin/contracts/contract/action_pass_allestimento.html', {
                **self.admin_site.each_context(request),
                'title': 'Invia PASS allestimento',
                'righe': righe,
                'gia_inviati': sum(1 for r in righe if r['c'].pass_allestimento_inviato_il),
                'eventi_incompleti': mancano,
                'cc': ', '.join(pa.CC_AMMINISTRAZIONE),
                'queryset': queryset,
                'action': 'action_invia_pass_allestimento',
                'opts': self.model._meta,
                'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            })

        reinvia = request.POST.get('reinvia') == '1'
        ok, saltati, errori = [], [], []
        for c in queryset:
            if c.status == ContractStatus.CANCELLED:
                saltati.append(f'{c.sponsor.legal_name} (annullato)')
                continue
            if c.pass_allestimento_inviato_il and not reinvia:
                saltati.append(f'{c.sponsor.legal_name} (già inviato)')
                continue
            try:
                pa.invia(c, utente=request.user)
                ok.append(c.sponsor.legal_name)
            except Exception as e:
                errori.append(f'{c.sponsor.legal_name}: {e}')
        if ok:
            self.message_user(request, f"PASS allestimento inviato a {len(ok)} Sponsor "
                                       f"(in copia ad amministrazione): {', '.join(ok)}.",
                              level=messages.SUCCESS)
        if saltati:
            self.message_user(request, f"Non inviato a: {', '.join(saltati)}.",
                              level=messages.WARNING)
        for e in errori:
            self.message_user(request, f"Errore — {e}", level=messages.ERROR)

    def anteprima_pass_view(self, request, object_id):
        from contracts.models import Contract
        from contracts.services import pass_allestimento as pa
        c = get_object_or_404(Contract, pk=object_id)
        oggetto, html = pa.anteprima(c)
        dest = pa.destinatario(c)
        barra = format_html(
            '<div style="font:14px sans-serif; background:#fff7d6; border-bottom:1px solid #e5c55a; '
            'padding:10px 16px;"><strong>ANTEPRIMA — non inviata.</strong> '
            'A: {} · CC: {} · Oggetto: {}</div>',
            getattr(dest, 'email', '(nessun indirizzo)'), ', '.join(pa.CC_AMMINISTRAZIONE), oggetto)
        return HttpResponse(barra + html)

    def get_urls(self):
        return [
            path('<path:object_id>/anteprima-pass-allestimento/',
                 self.admin_site.admin_view(self.anteprima_pass_view),
                 name='contracts_contract_anteprima_pass'),
        ] + super().get_urls()
