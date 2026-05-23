p = "portal/templates/portal/contract/detail.html"
c = open(p, encoding="utf-8").read()
if "checkout_dev_mark_paid" in c:
    print("pulsante gia' presente")
else:
    anc = """      <a href="{% url 'portal:checkout_card' contract.id %}" 
         class="bg-brand-500 hover:bg-brand-700 text-white font-medium px-5 py-2.5 rounded-md transition-colors">
        Paga ora
      </a>
    </div>"""
    new = """      <a href="{% url 'portal:checkout_card' contract.id %}" 
         class="bg-brand-500 hover:bg-brand-700 text-white font-medium px-5 py-2.5 rounded-md transition-colors">
        Paga ora
      </a>
      {% if debug %}
      <form method="post" action="{% url 'portal:checkout_dev_mark_paid' contract.id %}">
        {% csrf_token %}
        <button type="submit" class="bg-orange-500 hover:bg-orange-600 text-white font-medium px-5 py-2.5 rounded-md transition-colors">
          [DEV] Segna come pagato
        </button>
      </form>
      {% endif %}
    </div>"""
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("pulsante aggiunto")
    else:
        print("ATTENZIONE: blocco non trovato")
