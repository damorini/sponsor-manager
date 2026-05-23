p = "portal/templates/portal/catalog/event.html"
c = open(p, encoding="utf-8").read()
if "bg-gray-100 flex items-center justify-center" in c:
    print("segnaposto gia' presente")
else:
    anc = '''      {% if service.image %}
      <img src="{{ service.image.url }}" alt="{{ service.get_name }}" class="w-full h-40 object-cover">
      {% endif %}'''
    new = '''      {% if service.image %}
      <img src="{{ service.image.url }}" alt="{{ service.get_name }}" class="w-full h-40 object-cover">
      {% else %}
      <div class="w-full h-40 bg-gray-100 flex items-center justify-center text-gray-300">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3 16.5h18a1.5 1.5 0 001.5-1.5V6A1.5 1.5 0 0021 4.5H3A1.5 1.5 0 001.5 6v9A1.5 1.5 0 003 16.5z" />
        </svg>
      </div>
      {% endif %}'''
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("segnaposto aggiunto")
    else:
        print("ATTENZIONE: ancora non trovato")
