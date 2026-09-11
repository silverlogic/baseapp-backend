import pytest
from django.contrib.auth.models import User

from baseapp_auth.utils.normalize_permission import normalize_permission


@pytest.mark.django_db
class TestNormalizePermission:
    def test_full_permission_is_returned_as_is(self) -> None:
        assert normalize_permission("auth.change_user", User) == "auth.change_user"

    def test_short_action_is_expanded_with_model_name(self) -> None:
        assert normalize_permission("change", User) == "auth.change_user"

    def test_action_with_model_name_is_prefixed_with_app_label(self) -> None:
        assert normalize_permission("change_user", User) == "auth.change_user"
