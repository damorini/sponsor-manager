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
