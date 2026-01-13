# tests/test_group_admin_form.py
import pytest

from baseapp_auth.fields import GroupedPermissionField
from baseapp_auth.forms import UserChangeForm


@pytest.mark.django_db
def test_group_admin_form_uses_grouped_permission_field():
    form = UserChangeForm()

    assert "user_permissions" in form.fields
    assert isinstance(
        form.fields["user_permissions"],
        GroupedPermissionField,
    )
