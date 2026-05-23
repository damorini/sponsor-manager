import os
T = "portal/templates/portal"

# 1) Pulsante wishlist nel dettaglio servizio
p1 = os.path.join(T, "catalog/service_detail.html")
c = open(p1, encoding="utf-8").read()
if "wishlist/button.html" in c:
    print("[1] pulsante gia' presente, salto.")
else:
    ancora = "          </form>\n          {% else %}"
    nuovo = "          </form>\n\n          <div class=\"mt-3\">\n            {% include 'portal/wishlist/button.html' %}\n          </div>\n          {% else %}"
    if ancora in c:
        open(p1, "w", encoding="utf-8").write(c.replace(ancora, nuovo, 1))
        print("[1] pulsante wishlist aggiunto al dettaglio servizio.")
    else:
        print("[1] ATTENZIONE: punto di inserimento non trovato.")

# 2) Link Wishlist nel menu
p2 = os.path.join(T, "base.html")
c = open(p2, encoding="utf-8").read()
if "portal:wishlist_page" in c:
    print("[2] link menu gia' presente, salto.")
else:
    ancora = "          Contratti\n        </a>"
    nuovo = ancora + "\n        <a href=\"{% url 'portal:wishlist_page' %}\"\n           class=\"text-gray-700 hover:text-brand-500 font-medium\">\n          Wishlist\n        </a>"
    if ancora in c:
        open(p2, "w", encoding="utf-8").write(c.replace(ancora, nuovo, 1))
        print("[2] link Wishlist aggiunto al menu.")
    else:
        print("[2] ATTENZIONE: punto di inserimento menu non trovato.")
print("Fatto.")
