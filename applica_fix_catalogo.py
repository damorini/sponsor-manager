import os

MP = "catalog/models.py"
with open(MP, encoding="utf-8") as f:
    m = f.read()
if "def get_name" in m:
    print("[modello] get_name gia' presente, salto.")
else:
    ancora = '    def __str__(self):\n        return f"{self.translated(\'name\')} ({self.event.slug})"\n'
    blocco = ancora + '''
    def get_name(self, language=None):
        return self.translated('name', language)

    def get_description(self, language=None):
        return self.translated('description', language)
'''
    if ancora in m:
        open(MP, "w", encoding="utf-8").write(m.replace(ancora, blocco, 1))
        print("[modello] get_name/get_description aggiunti.")
    else:
        print("[modello] ATTENZIONE: __str__ non trovato, modello NON modificato.")

T = "portal/templates/portal"
def fix(path, subs):
    full = os.path.join(T, path)
    if not os.path.exists(full):
        print(f"[template] {path} non trovato"); return
    c = open(full, encoding="utf-8").read(); orig = c
    for a, b in subs: c = c.replace(a, b)
    if c != orig:
        open(full, "w", encoding="utf-8").write(c); print(f"[template] corretto: {path}")
    else:
        print(f"[template] nessuna modifica: {path}")

NAME = ("{{ service.name }}", "{{ service.get_name }}")
PRICE = ("{{ service.unit_price|floatformat:2 }}", "{{ service.base_price|floatformat:2 }}")
DESC = ("service.description", "service.get_description")
fix("catalog/list.html", [NAME, PRICE, DESC])
fix("catalog/service_detail.html", [NAME, PRICE, DESC])
fix("catalog/event.html", [NAME, PRICE, DESC])
fix("wishlist/list.html", [NAME, DESC])
fix("wishlist/button.html", [('data-service-name="{{ service.name }}"', 'data-service-name="{{ service.get_name }}"')])
print("Fatto.")
