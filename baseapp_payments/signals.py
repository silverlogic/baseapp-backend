from django.dispatch import Signal

# Sent once when Stripe confirms a one-time purchase's payment (``invoice.paid``).
# Receivers get ``sender`` (the concrete Purchase model) and ``purchase``. Projects use it
# to fulfil the order and notify people.
purchase_paid = Signal()

# Sent once when a one-time purchase's payment fails (``invoice.payment_failed``); the
# invoice is voided, so nothing is charged. Same arguments as ``purchase_paid``.
purchase_failed = Signal()
