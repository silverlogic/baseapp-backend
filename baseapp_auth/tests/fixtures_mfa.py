import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from trench.command.create_secret import create_secret_command
from trench.models import MFAMethod as MFAMethodModel

import baseapp_auth.tests.helpers as h

User = get_user_model()
UserFactory = h.get_user_factory()


def mfa_method_creator(
    user, method_name: str, is_primary: bool = True, **method_args
) -> MFAMethodModel:
    MFAMethod = apps.get_model("trench.MFAMethod")
    return MFAMethod.objects.create(
        user=user,
        secret=method_args.pop("secret", create_secret_command()),
        is_primary=is_primary,
        name=method_name,
        is_active=method_args.pop("is_active", True),
        **method_args,
    )


@pytest.fixture()
def active_user_with_application_otp():
    user = UserFactory()
    user.set_password("1234567890")
    user.is_active = True
    user.save()
    mfa_method_creator(user=user, method_name="app")
    return user
