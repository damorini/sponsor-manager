"""Risoluzione del percorso immagine indicato in una cella Excel.

Accetta percorsi completi (anche in stile Windows C:\\..., convertiti in
/mnt/c/...), oppure solo il nome del file se viene passata una cartella.
Usato da importa_servizi e importa_catalogo.
"""
import re
from pathlib import Path


def win_to_wsl(p):
    """Converte un percorso stile Windows (C:\\... o C:/...) nel percorso WSL
    equivalente (/mnt/c/...). Lascia invariati i percorsi gia' in stile Unix."""
    s = str(p or "").strip().strip('"').strip("'")
    if not s:
        return s
    m = re.match(r'^([A-Za-z]):[\\/](.*)$', s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace('\\', '/')
        return f"/mnt/{drive}/{rest}"
    return s.replace('\\', '/')


def resolve_image_path(immagine_raw, cartella_img=""):
    """Ritorna un Path al file immagine, o None se non trovato.

    - immagine_raw: contenuto della cella 'immagine' (percorso completo o nome file).
    - cartella_img: cartella opzionale (--immagini) dove cercare per solo-nome.
    """
    raw = win_to_wsl(immagine_raw)
    if not raw:
        return None
    cand = Path(raw).expanduser()
    if cand.is_file():
        return cand
    if cartella_img:
        sub = Path(win_to_wsl(cartella_img)).expanduser() / Path(raw).name
        if sub.is_file():
            return sub
    return None
