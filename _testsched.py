from contracts.tasks.scheduled import check_upcoming_deadlines, check_overdue_deadlines, check_abandoned_carts
print(">>> check_upcoming_deadlines")
check_upcoming_deadlines()
print(">>> check_overdue_deadlines")
check_overdue_deadlines()
print(">>> check_abandoned_carts")
check_abandoned_carts()
print("=== tutti i task schedulati eseguiti ===")
