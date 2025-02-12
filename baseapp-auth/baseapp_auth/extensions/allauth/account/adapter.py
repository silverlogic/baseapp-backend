import string

from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _

from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter


class AccountAdapter(DefaultAccountAdapter):
    def _generate_code(self):
        forbidden_chars = "0OI18B2ZAEU"
        allowed_chars = string.digits
        for ch in forbidden_chars:
            allowed_chars = allowed_chars.replace(ch, "")
        return get_random_string(length=6, allowed_chars=allowed_chars)


class MFAAdapter(DefaultMFAAdapter):
    error_messages = {
        **DefaultMFAAdapter.error_messages,
        "incorrect_code": _(
            "Invalid authentication code. Please check your MFA device and try again."
        ),
    }
