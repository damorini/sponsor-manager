# -*- coding: utf-8 -*-
"""
Servizi compilabili dal cliente - TAPPA 2 (form nel portale).
- form dei campi nella pagina Materiali (tipi: testo breve / testo lungo)
- salva le risposte in Deadline.content_data e marca 'Ricevuto'
- sistema il bug received_at -> usa mark_as_received(contact)
- dati sempre modificabili dal cliente; campi obbligatori validati
"""
import shutil, datetime
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def edit(path, repls):
    shutil.copy2(path, f"{path}.bak_{STAMP}")
    s = open(path, encoding='utf-8').read()
    for old, new in repls:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"[{path}] anchor x{n} (atteso 1): {old[:70]!r}")
        s = s.replace(old, new, 1)
    open(path, 'w', encoding='utf-8').write(s)
    print("  modificato:", path)

# ===== A) portal/views/materials.py =====
# A1 - arricchisci il dict del materiale con i campi-contenuto
edit("portal/views/materials.py", [(
"""        materials.append({
            'deadline': d,
            'documents': list(docs),
            'has_documents': docs.exists(),
            'is_completed': d.status in [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED],
        })""",
"""        content_fields = []
        for f in (d.content_schema or []):
            content_fields.append({
                'key': f.get('key'),
                'label': f.get('label', f.get('key')),
                'type': f.get('type', 'short_text'),
                'required': f.get('required', False),
                'help_text': f.get('help_text', ''),
                'value': (d.content_data or {}).get(f.get('key'), ''),
            })

        materials.append({
            'deadline': d,
            'documents': list(docs),
            'has_documents': docs.exists(),
            'is_completed': d.status in [DeadlineStatus.RECEIVED, DeadlineStatus.WAIVED],
            'content_fields': content_fields,
            'needs_content': getattr(d, 'submission_kind', 'file') in ('content', 'both'),
        })""")])

# A2 - fix received_at nell'upload file
edit("portal/views/materials.py", [(
"""    if uploaded_count > 0 and deadline.status != DeadlineStatus.RECEIVED:
        deadline.status = DeadlineStatus.RECEIVED
        deadline.received_at = timezone.now()
        deadline.save(update_fields=['status', 'received_at', 'updated_at'])""",
"""    if uploaded_count > 0 and deadline.status != DeadlineStatus.RECEIVED:
        deadline.mark_as_received(contact=getattr(request, 'contact', None))""")])

# A3 - nuova view: salvataggio dei campi compilati
with open("portal/views/materials.py", "a", encoding="utf-8") as f:
    f.write('''

# ============================================================================
# View: salvataggio campi compilati dal cliente
# ============================================================================

@sponsor_required
@require_POST
@transaction.atomic
def material_content_view(request, deadline_id):
    """Salva i campi di testo compilati dal cliente per una Deadline."""
    from contracts.models import Deadline, DeadlineStatus

    deadline = get_object_or_404(
        Deadline.objects.select_related('contract'),
        id=deadline_id,
    )
    if deadline.contract.sponsor_id != request.sponsor.id:
        return HttpResponseForbidden("Accesso negato.")
    if deadline.status == DeadlineStatus.WAIVED:
        messages.warning(request, "Questa richiesta e' stata esonerata.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)
    if getattr(deadline, 'submission_kind', 'file') not in ('content', 'both'):
        messages.error(request, "Questa richiesta non prevede dati da compilare.")
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    schema = deadline.content_schema or []
    data = dict(deadline.content_data or {})
    missing = []
    for fld in schema:
        key = fld.get('key')
        if not key:
            continue
        val = (request.POST.get('field_' + key) or '').strip()
        data[key] = val
        if fld.get('required') and not val:
            missing.append(fld.get('label', key))

    deadline.content_data = data
    deadline.save(update_fields=['content_data', 'updated_at'])

    if missing:
        messages.error(
            request,
            "Salvato, ma mancano i campi obbligatori: " + ", ".join(missing)
        )
        return redirect('portal:materials_list', contract_id=deadline.contract_id)

    if deadline.status != DeadlineStatus.RECEIVED:
        deadline.mark_as_received(contact=getattr(request, 'contact', None))
    messages.success(request, "Dati salvati per '%s'." % deadline.title)
    return redirect('portal:materials_list', contract_id=deadline.contract_id)
''')
print("  modificato: portal/views/materials.py (nuova view aggiunta)")

# ===== B) portal/urls.py =====
edit("portal/urls.py", [(
"""    path('materials/upload/<uuid:deadline_id>/', materials.material_upload_view,
         name='material_upload'),""",
"""    path('materials/upload/<uuid:deadline_id>/', materials.material_upload_view,
         name='material_upload'),
    path('materials/content/<uuid:deadline_id>/', materials.material_content_view,
         name='material_content'),""")])

# ===== C) template list.html =====
edit("portal/templates/portal/materials/list.html", [
  # C1 - fix received_at -> completed_at
  ('Ricevuto il {{ m.deadline.received_at|date:"d/m/Y" }}',
   'Ricevuto il {{ m.deadline.completed_at|date:"d/m/Y" }}'),
  # C2 - mostra l'upload solo per file/entrambi
  ('''      <!-- Form upload -->
      {% if m.deadline.status != 'waived' %}''',
   '''      <!-- Form upload (solo file / entrambi) -->
      {% if m.deadline.status != 'waived' and m.deadline.submission_kind != 'content' %}'''),
  # C3 - form dei campi dopo il blocco upload
  ('''            Carica file
          </button>
        </form>
      </div>
      {% endif %}''',
   '''            Carica file
          </button>
        </form>
      </div>
      {% endif %}

      <!-- Form campi da compilare (campi / entrambi) -->
      {% if m.deadline.status != 'waived' and m.needs_content %}
      <div class="px-5 py-4 bg-gray-50 border-t border-gray-100">
        <h4 class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
          Dati da compilare
        </h4>
        <form method="post" action="{% url 'portal:material_content' m.deadline.id %}" class="space-y-3">
          {% csrf_token %}
          {% for f in m.content_fields %}
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              {{ f.label }}{% if f.required %} <span class="text-red-500">*</span>{% endif %}
            </label>
            {% if f.type == 'long_text' %}
            <textarea name="field_{{ f.key }}" rows="4" {% if f.required %}required{% endif %}
                      class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">{{ f.value }}</textarea>
            {% else %}
            <input type="text" name="field_{{ f.key }}" value="{{ f.value }}" {% if f.required %}required{% endif %}
                   class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
            {% endif %}
            {% if f.help_text %}<p class="text-xs text-gray-500 mt-1">{{ f.help_text }}</p>{% endif %}
          </div>
          {% endfor %}
          <button type="submit"
                  class="bg-brand-500 hover:bg-brand-700 text-white font-medium px-5 py-2 rounded-md text-sm transition-colors">
            Salva i dati
          </button>
        </form>
      </div>
      {% endif %}'''),
])

print("FATTO")
