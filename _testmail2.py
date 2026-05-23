from contracts.payments import Payment
print("TOTALE payment:", Payment.objects.count())
for p in Payment.objects.all()[:5]:
    print(p.id, '| stato:', p.status, '| contratto:', p.contract.contract_number)
