p = "portal/urls.py"
c = open(p, encoding="utf-8").read()
if "checkout_dev_mark_paid" in c:
    print("rotta gia' presente")
else:
    anc = """    path('checkout/success/<uuid:payment_id>/',
         checkout.paypal_return, name='checkout_success'),
]"""
    new = """    path('checkout/success/<uuid:payment_id>/',
         checkout.paypal_return, name='checkout_success'),
    path('checkout/dev-mark-paid/<uuid:contract_id>/',
         checkout.dev_mark_paid, name='checkout_dev_mark_paid'),
]"""
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("rotta aggiunta")
    else:
        print("ATTENZIONE: ancora non trovata")
