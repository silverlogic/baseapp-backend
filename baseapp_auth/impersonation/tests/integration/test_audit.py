import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from baseapp_auth.tests.factories import UserFactory

from ...models import ImpersonationSession
from ...services import record_action
from ..fixtures import bearer

pytestmark = pytest.mark.django_db


def test_deleting_the_impersonator_keeps_the_audit_trail(client, superuser, start_session) -> None:
    session, tokens = start_session()
    record_action(session, method="PATCH", path="/v1/users/1", status_code=200)
    superuser.delete()

    session.refresh_from_db()
    assert session.impersonator is None
    assert session.actions.count() == 1
    # The session's tokens stop working with it.
    assert client.get("/v1/users/me", **bearer(tokens["access"])).status_code == 401


def test_deleting_the_target_deletes_their_sessions(member, start_session) -> None:
    session, _tokens = start_session()
    member.delete()
    assert not ImpersonationSession.objects.filter(pk=session.pk).exists()


@pytest.mark.parametrize("codenames, offered", [(["view"], False), (["view", "change"], True)])
def test_revoke_action_needs_the_change_permission(codenames, offered) -> None:
    staff = UserFactory(is_staff=True)
    staff.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="baseapp_impersonation",
            codename__in=[f"{codename}_impersonationsession" for codename in codenames],
        )
    )
    request = RequestFactory().get("/admin/")
    request.user = UserFactory._meta.model.objects.get(pk=staff.pk)
    model_admin = site._registry[ImpersonationSession]
    assert ("revoke_sessions" in model_admin.get_actions(request)) is offered
