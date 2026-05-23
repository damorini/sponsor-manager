from contracts.payments import Payment
p = Payment.objects.get(id='3d6b4035-bca8-4f5f-b1b8-d8aae6a54e19')
print("stato prima:", p.status)
p.mark_succeeded()
print("=== mark_succeeded eseguito, stato dopo:", p.status)
