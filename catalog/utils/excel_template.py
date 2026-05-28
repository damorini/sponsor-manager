"""Genera al volo i template Excel per gli import."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.comments import Comment


def build_template_servizi_workbook():
    """Crea e ritorna un openpyxl Workbook col template Excel per importa_servizi."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Servizi"

    headers = [
        ("evento_slug", "OBBLIGATORIO. Slug dell'evento, es. AITEB2026"),
        ("code", "OBBLIGATORIO. Codice univoco per evento, es. TAVOLO_STD"),
        ("nome_it", "OBBLIGATORIO. Nome in italiano"),
        ("nome_en", "Opzionale. Nome in inglese"),
        ("descrizione_it", "Opzionale. Descrizione italiano"),
        ("descrizione_en", "Opzionale. Descrizione inglese"),
        ("categoria", "Opzionale. Categoria libera (es. arredo, grafica, tecnico)"),
        ("categoria_contabile", "Default 'altro'. Valori: viaggio_partecipanti, "
         "viaggio_relatori, affitto_sala, stand, coffee_break, scheda_tecnica, "
         "quota_iscrizione, altro"),
        ("prezzo_base", "OBBLIGATORIO. Prezzo unitario in euro (es. 100.00)"),
        ("iva_percento", "IVA in percentuale (default 22)"),
        ("attivo", "s/n (default s)"),
        ("quantita_max", "Quantita' massima vendibile per contratto (vuoto = illimitata)"),
        ("ordine", "Ordine di visualizzazione (numero, default 0)"),
        ("pricing_mode", "Default 'fixed'. Valori: fixed, quantity, tiered"),
    ]

    header_fill = PatternFill(start_color="417690", end_color="417690", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for i, (name, comment) in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.comment = Comment(comment, "Sponsor Manager")

    esempio1 = ["AITEB2026", "TAVOLO_DEMO", "Tavolo standard", "Standard table",
                "Tavolo 80x80 cm, bianco", "80x80 cm white table",
                "arredo", "altro", 100.00, 22, "s", "", 10, "fixed"]
    esempio2 = ["AITEB2026", "FARETTO_DEMO", "Faretto LED", "LED spotlight",
                "Faretto LED 30W", "LED spotlight 30W",
                "tecnico", "altro", 25.00, 22, "s", 50, 20, "fixed"]
    for col, v in enumerate(esempio1, start=1):
        ws.cell(row=2, column=col, value=v)
    for col, v in enumerate(esempio2, start=1):
        ws.cell(row=3, column=col, value=v)

    larghezze = [14, 18, 22, 22, 28, 28, 14, 22, 14, 14, 8, 14, 10, 14]
    for i, w in enumerate(larghezze, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    ws2 = wb.create_sheet("Istruzioni")
    istr = [
        "IMPORT SERVIZI - Istruzioni",
        "",
        "1. Le PRIME 2 RIGHE del foglio 'Servizi' sono esempi: cancellali o sovrascrivili.",
        "2. Compila una riga per ogni servizio da importare/aggiornare.",
        "3. Colonne OBBLIGATORIE: evento_slug, code, nome_it, prezzo_base.",
        "4. evento_slug: lo slug dell'evento gia' esistente (es. AITEB2026).",
        "5. code: univoco per evento. Se esiste -> AGGIORNA, sennò -> CREA.",
        "6. categoria_contabile valida (default 'altro'):",
        "   viaggio_partecipanti / viaggio_relatori / affitto_sala / stand /",
        "   coffee_break / scheda_tecnica / quota_iscrizione / altro",
        "7. pricing_mode valida (default 'fixed'): fixed / quantity / tiered",
        "8. attivo: s/n (default s). Numeri: usa il punto o la virgola decimale.",
        "",
        "Lancio:",
        "  python manage.py importa_servizi --file <percorso_file.xlsx> --dry-run",
        "  (verifica cosa farebbe, poi togli --dry-run per eseguire davvero)",
    ]
    for r, riga in enumerate(istr, start=1):
        ws2.cell(row=r, column=1, value=riga)
    ws2.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws2.column_dimensions["A"].width = 80
    return wb


def build_template_stand_workbook():
    """Crea e ritorna un openpyxl Workbook col template Excel per importa_stand."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment

    wb = Workbook()
    ws = wb.active
    ws.title = "Stand"

    headers = [
        ("evento_slug", "OBBLIGATORIO. Slug dell'evento, es. AITEB2026"),
        ("code", "OBBLIGATORIO. Codice univoco per evento, es. A-12"),
        ("blocco_code", "Opzionale. Codice del blocco (StandBlock) cui appartiene lo stand"),
        ("prezzo_base", "OBBLIGATORIO. Prezzo base in euro (es. 1500.00)"),
        ("larghezza_m", "Opzionale. Larghezza in metri (es. 3)"),
        ("profondita_m", "Opzionale. Profondita' in metri (es. 2)"),
        ("tipologia", "Opzionale. Testo libero (es. corner_premium, linear, island, custom)"),
        ("stato", "Default 'available'. Valori: available, reserved, assigned, unavailable"),
        ("allaccio_elettrico", "s/n (default n)"),
        ("potenza_kw", "Opzionale. Potenza in kW (es. 3)"),
        ("allaccio_idrico", "s/n (default n)"),
        ("internet", "s/n (default n)"),
        ("altezza_max_m", "Opzionale. Altezza massima in metri"),
        ("descrizione_preventivo", "Opzionale. Descrizione mostrata nel preventivo"),
    ]

    header_fill = PatternFill(start_color="417690", end_color="417690", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for i, (name, comment) in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.comment = Comment(comment, "Sponsor Manager")

    esempio1 = ["AITEB2026", "A-01", "", 1500.00, 3, 2, "linear", "available",
                "s", 3, "n", "s", 2.5, "Stand lineare 3x2 m, fronte corridoio"]
    esempio2 = ["AITEB2026", "A-02", "", 2500.00, 4, 4, "island", "available",
                "s", 6, "s", "s", 3.0, "Isola 4x4 m, doppio fronte"]
    for col, v in enumerate(esempio1, start=1):
        ws.cell(row=2, column=col, value=v)
    for col, v in enumerate(esempio2, start=1):
        ws.cell(row=3, column=col, value=v)

    larghezze = [14, 10, 14, 14, 12, 12, 16, 14, 18, 12, 16, 10, 14, 32]
    for i, w in enumerate(larghezze, start=1):
        ws.column_dimensions[chr(64 + i)].width = w

    ws2 = wb.create_sheet("Istruzioni")
    istr = [
        "IMPORT STAND - Istruzioni",
        "",
        "1. Le PRIME 2 RIGHE del foglio 'Stand' sono esempi: cancellali o sovrascrivili.",
        "2. Compila una riga per ogni stand da importare/aggiornare.",
        "3. Colonne OBBLIGATORIE: evento_slug, code, prezzo_base.",
        "4. evento_slug: lo slug dell'evento gia' esistente (es. AITEB2026).",
        "5. code: univoco per evento. Se esiste -> AGGIORNA, sennò -> CREA.",
        "6. blocco_code: opzionale. Se valorizzato, lo stand viene collegato al blocco",
        "   (StandBlock) con quel codice NELLO STESSO evento. Se il blocco non esiste -> errore.",
        "7. stato valido (default 'available'): available / reserved / assigned / unavailable",
        "8. allaccio_elettrico / allaccio_idrico / internet: s/n (default n).",
        "9. Numeri: usa il punto o la virgola decimale.",
        "",
        "Lancio:",
        "  python manage.py importa_stand --file <percorso_file.xlsx> --dry-run",
        "  (verifica cosa farebbe, poi togli --dry-run per eseguire davvero)",
    ]
    for r, riga in enumerate(istr, start=1):
        ws2.cell(row=r, column=1, value=riga)
    ws2.cell(row=1, column=1).font = Font(bold=True, size=14)
    ws2.column_dimensions["A"].width = 80
    return wb


def _norm_bool_out(v):
    return 's' if v else 'n'


def export_servizi_workbook(event):
    """Workbook con i servizi esistenti di un evento (stesse colonne del template)."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font
    from catalog.models import Service

    wb = Workbook()
    ws = wb.active
    ws.title = "servizi"
    headers = ["evento_slug", "code", "nome_it", "nome_en", "descrizione_it",
               "descrizione_en", "categoria", "categoria_contabile", "prezzo_base",
               "iva_percento", "attivo", "quantita_max", "ordine", "pricing_mode"]
    header_fill = PatternFill(start_color="417690", end_color="417690", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for i, name in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=name)
        c.fill = header_fill
        c.font = header_font

    r = 2
    for s in Service.objects.filter(event=event).order_by('display_order', 'code'):
        nome = s.name if isinstance(s.name, dict) else {}
        desc = s.description if isinstance(s.description, dict) else {}
        ws.cell(row=r, column=1, value=event.slug)
        ws.cell(row=r, column=2, value=s.code)
        ws.cell(row=r, column=3, value=nome.get('it', ''))
        ws.cell(row=r, column=4, value=nome.get('en', ''))
        ws.cell(row=r, column=5, value=desc.get('it', ''))
        ws.cell(row=r, column=6, value=desc.get('en', ''))
        ws.cell(row=r, column=7, value=s.category or '')
        ws.cell(row=r, column=8, value=s.accounting_category or '')
        ws.cell(row=r, column=9, value=float(s.base_price) if s.base_price is not None else '')
        ws.cell(row=r, column=10, value=float(s.vat_rate) if s.vat_rate is not None else '')
        ws.cell(row=r, column=11, value=_norm_bool_out(s.is_active))
        ws.cell(row=r, column=12, value=s.max_quantity if s.max_quantity is not None else '')
        ws.cell(row=r, column=13, value=s.display_order or 0)
        ws.cell(row=r, column=14, value=s.pricing_mode or 'fixed')
        r += 1

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18
    return wb


def export_stand_workbook(event):
    """Workbook con gli stand esistenti di un evento (stesse colonne del template)."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font
    from venues.models import Stand

    wb = Workbook()
    ws = wb.active
    ws.title = "stand"
    headers = ["evento_slug", "code", "blocco_code", "prezzo_base", "larghezza_m",
               "profondita_m", "tipologia", "stato", "allaccio_elettrico", "potenza_kw",
               "allaccio_idrico", "internet", "altezza_max_m", "descrizione_preventivo"]
    header_fill = PatternFill(start_color="417690", end_color="417690", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for i, name in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=name)
        c.fill = header_fill
        c.font = header_font

    r = 2
    for st in Stand.objects.filter(event=event).select_related('stand_block').order_by('code'):
        ws.cell(row=r, column=1, value=event.slug)
        ws.cell(row=r, column=2, value=st.code)
        ws.cell(row=r, column=3, value=st.stand_block.code if st.stand_block_id else '')
        ws.cell(row=r, column=4, value=float(st.base_price) if st.base_price is not None else '')
        ws.cell(row=r, column=5, value=float(st.width_meters) if st.width_meters is not None else '')
        ws.cell(row=r, column=6, value=float(st.depth_meters) if st.depth_meters is not None else '')
        ws.cell(row=r, column=7, value=st.stand_type or '')
        ws.cell(row=r, column=8, value=st.status or 'available')
        ws.cell(row=r, column=9, value=_norm_bool_out(st.has_power))
        ws.cell(row=r, column=10, value=float(st.power_kw) if st.power_kw is not None else '')
        ws.cell(row=r, column=11, value=_norm_bool_out(st.has_water))
        ws.cell(row=r, column=12, value=_norm_bool_out(st.has_internet))
        ws.cell(row=r, column=13, value=float(st.max_height_meters) if st.max_height_meters is not None else '')
        ws.cell(row=r, column=14, value=st.quote_description or '')
        r += 1

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18
    return wb
