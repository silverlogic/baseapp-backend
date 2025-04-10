import re

from django.contrib.auth.password_validation import (
    get_password_validators,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from baseapp_auth.models import PasswordValidation


class MustContainCapitalLetterValidator:
    def __init__(self, min_length=1):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(re.findall(r"[A-Z]", password)) < self.min_length:
            raise ValidationError(
                _("This password must contain at least %(min_length)d capital letter characters."),
                code="password_no_upper",
                params={"min_length": self.min_length},
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least %(min_length)d capital letter characters."
            % {"min_length": self.min_length}
        )


class MustContainSpecialCharacterValidator:
    def __init__(self, min_length=1):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(re.findall(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password)) < self.min_length:
            raise ValidationError(
                _("This password must contain at least %(min_length)d special characters."),
                code="password_no_special_character",
                params={"min_length": self.min_length},
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least %(min_length)d special characters."
            % {"min_length": self.min_length}
        )


def apply_password_validators(password, user=None):
    validators = PasswordValidation.objects.filter(is_active=True)
    password_validators = []

    for validator in validators:
        data = {
            "NAME": validator.name,
        }
        if validator.options:
            data["OPTIONS"] = validator.options
        password_validators.append(data)
    return validate_password(password, user, get_password_validators(password_validators))
