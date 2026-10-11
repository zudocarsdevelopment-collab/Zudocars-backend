# Operational accounts

Deploy this app together with the UI, run `python manage.py migrate`, then restart the backend service. No payment receipts are invented for historical bookings: enter their actual receipts and refunds with the original transaction dates/references.

The authenticated `/api/accounts/summary/` endpoint supplies all-time INR totals and complete booking, payment, manual expense, and maintenance expense histories.

- Booked revenue: booking totals for confirmed and completed bookings. Pending and cancelled bookings contribute zero.
- Net receipts: recorded receipts minus recorded refunds, including deposits on pending bookings.
- Outstanding: sum of `max(booked amount - net receipts, 0)` per booking. Credits on one booking never offset another booking's debt.
- Customer credits: sum of `max(net receipts - booked amount, 0)` per booking. This includes deposits, overpayments and amounts awaiting refund after cancellation.
- Expenses: active manual expenses plus existing ServiceRecord total costs, counted once. Record additional maintenance costs only if they are absent from Service History.
- Net balance: booked revenue minus expenses. This is an operational margin, not a reconciled bank balance; neither bookings nor service records prove cash movement.

`POST /api/accounts/payments/` records a positive receipt or refund against a booking reference. `POST /api/accounts/expenses/` records a positive expense with category, description and optional vehicle. Both require a client-generated UUID `request_id`; repeating the same submission returns the original entry. Changing its data with the same UUID is rejected. Transactions use India calendar dates and cannot be future dated.

`POST /api/accounts/{payments|expenses}/{id}/void/` requires a reason. Entries cannot be edited or deleted through the API or Django admin. Voids preserve creator, creation time, voiding operator, void time and reason. Refunds cannot exceed a booking's net receipts, and receipts cannot be voided while they support active refunds. Booking row locks protect those checks against concurrent ledger changes.

Access follows the existing dashboard policy: all authenticated dashboard users have access. These records track operational receipts and expenses; they do not implement bank reconciliation, tax filing, payroll, supplier payables, or a double-entry general ledger.

Tests: `python manage.py test accounting`. Include booking, maintenance and fleet suites for integration regression coverage. Tests should use an isolated database, never the live database.
