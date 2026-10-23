"""
Signals for project audit logs. All are sent with ``sender`` set to the model class.

- ``impersonation_started(session, request)``
- ``impersonation_ended(session, reason, request)``; ``request`` is ``None`` when a session
  is found expired.
- ``impersonation_denied(impersonator, target, request)``: a start the
  ``CAN_IMPERSONATE`` hook refused.
- ``impersonation_action(action, session, request)``: a write made during a session.
"""

from django.dispatch import Signal

impersonation_started = Signal()
impersonation_ended = Signal()
impersonation_denied = Signal()
impersonation_action = Signal()
