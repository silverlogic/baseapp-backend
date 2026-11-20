"""
Signals sent by the MFA views in `baseapp_auth.rest_framework.mfa.views` after a change succeeds.

Every signal is sent with `sender` set to the view class and these keyword arguments:

- `user`: the user whose MFA methods changed.
- `method`: the MFA method name (e.g. "app", "email", "sms_twilio").
- `request`: the DRF request that made the change.

`mfa_primary_method_changed` also sends `previous_method`: the name of the primary method before
the change, or `None` when the user had none.
"""

from django.dispatch import Signal

__all__ = [
    "mfa_method_activated",
    "mfa_method_deactivated",
    "mfa_primary_method_changed",
    "mfa_backup_codes_regenerated",
]

# Sent when a user confirms the activation of a method (POST <method>/activate/confirm/).
mfa_method_activated = Signal()

# Sent when a user deactivates a method (POST <method>/deactivate/).
mfa_method_deactivated = Signal()

# Sent when a user picks another primary method (POST change-primary-method/). Not sent when the
# method was already the primary one.
mfa_primary_method_changed = Signal()

# Sent when a user regenerates the backup codes of a method (POST <method>/codes/regenerate/).
mfa_backup_codes_regenerated = Signal()
