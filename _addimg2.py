p = "portal/templates/portal/catalog/service_detail.html"
c = open(p, encoding="utf-8").read()
if "service.image" in c:
    print("gia' presente")
else:
    anc = '''      <!-- Descrizione -->
      <div class="lg:col-span-2">
        {% if service.get_description %}'''
    add = '''      <!-- Descrizione -->
      <div class="lg:col-span-2">
        {% if service.image %}
        <img src="{{ service.image.url }}" alt="{{ service.get_name }}" class="w-full max-h-80 object-cover rounded-lg mb-5">
        {% endif %}
        {% if service.get_description %}'''
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,add,1))
        print("immagine aggiunta al dettaglio")
    else:
        print("ATTENZIONE: ancora non trovata")
