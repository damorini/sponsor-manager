def patch(path, vecchio, nuovo, et):
    c = open(path, encoding="utf-8").read()
    if nuovo in c:
        print(f"[{et}] gia' fatto"); return
    if vecchio in c:
        open(path,"w",encoding="utf-8").write(c.replace(vecchio,nuovo,1))
        print(f"[{et}] corretto")
    else:
        print(f"[{et}] ATTENZIONE: non trovato")

CL = "portal/templates/portal/dashboard/contracts_list.html"
patch(CL,
  '{{ total_count }} contratto{{ total_count|pluralize:"i" }}',
  '{{ total_count }} contratt{{ total_count|pluralize:"o,i" }}',
  "refuso contratti")
patch(CL,
  '{{ c.pending_deadlines_count }} scadenz{{ c.pending_deadlines_count|pluralize:"a,e" }} aperta',
  '{{ c.pending_deadlines_count }} scadenz{{ c.pending_deadlines_count|pluralize:"a,e" }} apert{{ c.pending_deadlines_count|pluralize:"a,e" }}',
  "refuso scadenze")

B = "portal/templates/portal/base.html"
patch(B,
  '''      <a href="{% url 'portal:contracts_list' %}"
         class="block px-3 py-2 text-gray-700 hover:bg-gray-50 rounded">Contratti</a>''',
  '''      <a href="{% url 'portal:contracts_list' %}"
         class="block px-3 py-2 text-gray-700 hover:bg-gray-50 rounded">Contratti</a>
      <a href="{% url 'portal:wishlist_page' %}"
         class="block px-3 py-2 text-gray-700 hover:bg-gray-50 rounded">Wishlist</a>''',
  "wishlist mobile")
print("Fatto.")
