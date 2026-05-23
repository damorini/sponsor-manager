p = "catalog/admin.py"
c = open(p, encoding="utf-8").read()
vecchio = """    def pricing_display(self, obj):
        if obj.pricing_mode == PricingMode.FIXED:
            return format_html('<strong>€ {:,.2f}</strong>', obj.base_price)
        if obj.pricing_mode == PricingMode.QUANTITY:
            return format_html('€ {:,.2f} <small>× q.tà</small>', obj.base_price)
        if obj.pricing_mode == PricingMode.TIERED:
            return format_html(
                '<small>scaglioni</small> <strong>€ {:,.2f}+</strong>',
                obj.base_price
            )
        return '—'"""
nuovo = """    def pricing_display(self, obj):
        prezzo = f"{obj.base_price:,.2f}"
        if obj.pricing_mode == PricingMode.FIXED:
            return format_html('<strong>€ {}</strong>', prezzo)
        if obj.pricing_mode == PricingMode.QUANTITY:
            return format_html('€ {} <small>× q.tà</small>', prezzo)
        if obj.pricing_mode == PricingMode.TIERED:
            return format_html(
                '<small>scaglioni</small> <strong>€ {}+</strong>',
                prezzo
            )
        return '—'"""
if vecchio in c:
    open(p,"w",encoding="utf-8").write(c.replace(vecchio,nuovo,1))
    print("pricing_display corretto")
elif "prezzo = f" in c:
    print("gia' corretto")
else:
    print("ATTENZIONE: blocco non trovato")
