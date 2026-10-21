import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

import pytest
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.dispatch import Signal
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from trench import views as trench_views
from trench.backends.provider import get_mfa_handler

import baseapp_auth.tests.helpers as h
from baseapp_auth.rest_framework.mfa import views as mfa_views
from baseapp_auth.rest_framework.mfa.policy import MFAPolicy, get_mfa_policy
from baseapp_auth.rest_framework.mfa.signals import (
    mfa_backup_codes_regenerated,
    mfa_method_activated,
    mfa_method_deactivated,
    mfa_primary_method_changed,
)
from baseapp_auth.rest_framework.urls.mfa import get_urlpatterns
from baseapp_auth.tests.fixtures_mfa import mfa_method_creator

pytestmark = pytest.mark.django_db

MFA_URL = "/v1/auth/mfa/"
POLICY_PATH = "baseapp_auth.tests.integration.test_mfa."


class RequiredMFAPolicy(MFAPolicy):
    def is_required(self, user) -> bool:
        return True


class NoPrimaryChangePolicy(MFAPolicy):
    def can_change_primary(self, user, method: str) -> tuple[bool, str | None]:
        return False, "Ask an administrator to change your primary method."


class SilentRefusalPolicy(MFAPolicy):
    def can_deactivate(self, user, method: str) -> tuple[bool, str | None]:
        return False, None


class GatedRequiredMFAPolicy(RequiredMFAPolicy):
    """Calls `gates[method]` after deciding, so a test can line up two concurrent requests."""

    gates: dict[str, Callable[[], None]] = {}

    def can_deactivate(self, user, method: str) -> tuple[bool, str | None]:
        result = super().can_deactivate(user, method)
        gate = self.gates.get(method)
        if gate:
            gate()
        return result


class CustomDeactivationView(mfa_views.MFAMethodDeactivationView):
    pass


BACKUP_CODE = "12345678"


@contextmanager
def capture(signal: Signal) -> Iterator[list[dict[str, Any]]]:
    calls = []

    def receiver(**kwargs) -> None:
        calls.append(kwargs)

    signal.connect(receiver, weak=False)
    try:
        yield calls
    finally:
        signal.disconnect(receiver)


def code_for(mfa_method) -> str:
    return get_mfa_handler(mfa_method=mfa_method).create_code()


def with_backup_code(mfa_method):
    mfa_method.backup_codes = [make_password(BACKUP_CODE)]
    mfa_method.save()
    return mfa_method


def has_backup_code(mfa_method) -> bool:
    mfa_method.refresh_from_db()
    return any(code for code in mfa_method.backup_codes)


class TestMFASignals:
    def test_confirming_activation_sends_mfa_method_activated(self, user_client) -> None:
        mfa = mfa_method_creator(user_client.user, "app", is_primary=False, is_active=False)
        with capture(mfa_method_activated) as calls:
            r = user_client.post(f"{MFA_URL}app/activate/confirm/", {"code": code_for(mfa)})
        h.responseOk(r)
        assert len(calls) == 1
        assert calls[0]["sender"] is mfa_views.MFAMethodConfirmActivationView
        assert calls[0]["user"] == user_client.user
        assert calls[0]["method"] == "app"
        assert calls[0]["request"] is not None

    def test_invalid_activation_code_sends_nothing(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app", is_primary=False, is_active=False)
        with capture(mfa_method_activated) as calls:
            r = user_client.post(f"{MFA_URL}app/activate/confirm/", {"code": "000000"})
        h.responseBadRequest(r)
        assert calls == []

    def test_deactivating_sends_mfa_method_deactivated(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        with capture(mfa_method_deactivated) as calls:
            r = user_client.post(f"{MFA_URL}app/deactivate/")
        assert r.status_code == status.HTTP_204_NO_CONTENT
        assert len(calls) == 1
        assert calls[0]["sender"] is mfa_views.MFAMethodDeactivationView
        assert calls[0]["user"] == user_client.user
        assert calls[0]["method"] == "app"
        assert not user_client.user.mfa_methods.get(name="app").is_active

    def test_failed_deactivation_sends_nothing(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        mfa_method_creator(user_client.user, "email", is_primary=False)
        with capture(mfa_method_deactivated) as calls:
            # trench refuses to deactivate the primary method while another one is active
            r = user_client.post(f"{MFA_URL}app/deactivate/")
        h.responseBadRequest(r)
        assert calls == []

    def test_regenerating_backup_codes_sends_signal(self, user_client) -> None:
        mfa = mfa_method_creator(user_client.user, "app")
        with capture(mfa_backup_codes_regenerated) as calls:
            r = user_client.post(f"{MFA_URL}app/codes/regenerate/", {"code": code_for(mfa)})
        h.responseOk(r)
        assert r.data["backup_codes"]
        assert len(calls) == 1
        assert calls[0]["sender"] is mfa_views.MFAMethodBackupCodesRegenerationView
        assert calls[0]["method"] == "app"

    def test_failed_backup_codes_regeneration_sends_nothing(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        with capture(mfa_backup_codes_regenerated) as calls:
            r = user_client.post(f"{MFA_URL}app/codes/regenerate/", {"code": "000000"})
        h.responseBadRequest(r)
        assert calls == []

    def test_changing_primary_method_sends_signal(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        email = mfa_method_creator(user_client.user, "email", is_primary=False)
        with capture(mfa_primary_method_changed) as calls:
            r = user_client.post(
                f"{MFA_URL}change-primary-method/", {"method": "email", "code": code_for(email)}
            )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.data
        assert user_client.user.mfa_methods.get(is_primary=True).name == "email"
        assert len(calls) == 1
        assert calls[0]["sender"] is mfa_views.MFAPrimaryMethodChangeView
        assert calls[0]["user"] == user_client.user
        assert calls[0]["method"] == "email"
        assert calls[0]["previous_method"] == "app"

    def test_making_the_primary_method_primary_again_sends_nothing(self, user_client) -> None:
        app = mfa_method_creator(user_client.user, "app")
        mfa_method_creator(user_client.user, "email", is_primary=False)
        with capture(mfa_primary_method_changed) as calls:
            r = user_client.post(
                f"{MFA_URL}change-primary-method/", {"method": "app", "code": code_for(app)}
            )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.data
        assert user_client.user.mfa_methods.get(is_primary=True).name == "app"
        assert calls == []

    def test_changing_primary_to_an_inactive_method_sends_nothing(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        email = mfa_method_creator(user_client.user, "email", is_primary=False, is_active=False)
        with capture(mfa_primary_method_changed) as calls:
            r = user_client.post(
                f"{MFA_URL}change-primary-method/", {"method": "email", "code": code_for(email)}
            )
        h.responseBadRequest(r)
        assert calls == []


class TestMFAPolicy:
    def test_default_policy_allows_removing_the_last_method(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        r = user_client.post(f"{MFA_URL}app/deactivate/")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "RequiredMFAPolicy")
    def test_required_policy_keeps_the_last_method(self, user_client) -> None:
        mfa = mfa_method_creator(user_client.user, "app")
        with capture(mfa_method_deactivated) as calls:
            r = user_client.post(f"{MFA_URL}app/deactivate/", {"code": code_for(mfa)})
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == [str(MFAPolicy.last_method_message)]
        assert user_client.user.mfa_methods.get(name="app").is_active
        assert calls == []

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "RequiredMFAPolicy")
    def test_required_policy_asks_for_a_code(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        email = mfa_method_creator(user_client.user, "email", is_primary=False)

        r = user_client.post(f"{MFA_URL}email/deactivate/")
        h.responseBadRequest(r)
        assert "code" in r.data
        assert user_client.user.mfa_methods.get(name="email").is_active

        r = user_client.post(f"{MFA_URL}email/deactivate/", {"code": code_for(email)})
        assert r.status_code == status.HTTP_204_NO_CONTENT
        assert not user_client.user.mfa_methods.get(name="email").is_active

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "NoPrimaryChangePolicy")
    def test_policy_can_refuse_a_primary_method_change(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        email = mfa_method_creator(user_client.user, "email", is_primary=False)
        r = user_client.post(
            f"{MFA_URL}change-primary-method/", {"method": "email", "code": code_for(email)}
        )
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == ["Ask an administrator to change your primary method."]
        assert user_client.user.mfa_methods.get(is_primary=True).name == "app"

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "SilentRefusalPolicy")
    def test_refusal_without_reason_gets_a_generic_message(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        r = user_client.post(f"{MFA_URL}app/deactivate/")
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == ["This change is not allowed."]

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "RequiredMFAPolicy")
    def test_refused_deactivation_keeps_the_backup_code(self, user_client) -> None:
        app = with_backup_code(mfa_method_creator(user_client.user, "app"))
        r = user_client.post(f"{MFA_URL}app/deactivate/", {"code": BACKUP_CODE})
        h.responseBadRequest(r)
        assert r.data["non_field_errors"] == [str(MFAPolicy.last_method_message)]
        assert has_backup_code(app)

    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "NoPrimaryChangePolicy")
    def test_refused_primary_change_keeps_the_backup_code(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        email = with_backup_code(mfa_method_creator(user_client.user, "email", is_primary=False))
        r = user_client.post(
            f"{MFA_URL}change-primary-method/", {"method": "email", "code": BACKUP_CODE}
        )
        h.responseBadRequest(r)
        assert has_backup_code(email)

    def test_deactivation_refused_by_trench_keeps_the_backup_code(self, user_client) -> None:
        app = with_backup_code(mfa_method_creator(user_client.user, "app"))
        mfa_method_creator(user_client.user, "email", is_primary=False)
        # trench refuses to deactivate the primary method while another one is active
        r = user_client.post(f"{MFA_URL}app/deactivate/", {"code": BACKUP_CODE})
        h.responseBadRequest(r)
        assert has_backup_code(app)

    def test_accepted_deactivation_uses_up_the_backup_code(self, user_client) -> None:
        app = with_backup_code(mfa_method_creator(user_client.user, "app"))
        r = user_client.post(f"{MFA_URL}app/deactivate/", {"code": BACKUP_CODE})
        assert r.status_code == status.HTTP_204_NO_CONTENT
        assert not has_backup_code(app)

    def test_get_mfa_policy_defaults_to_mfa_policy(self) -> None:
        assert type(get_mfa_policy()) is MFAPolicy

    @override_settings(BASEAPP_AUTH_MFA_POLICY=RequiredMFAPolicy)
    def test_get_mfa_policy_accepts_a_class(self) -> None:
        assert isinstance(get_mfa_policy(), RequiredMFAPolicy)

    def test_default_policy_answers(self) -> None:
        user = h.get_user_factory()()
        policy = MFAPolicy()
        assert policy.is_required(user) is False
        assert policy.can_deactivate(user, "app") == (True, None)
        assert policy.can_change_primary(user, "app") == (True, None)

    def test_required_policy_allows_removing_one_of_several_methods(self) -> None:
        user = h.get_user_factory()()
        mfa_method_creator(user, "app")
        mfa_method_creator(user, "email", is_primary=False)
        assert RequiredMFAPolicy().can_deactivate(user, "email") == (True, None)

    def test_required_policy_allows_naming_an_inactive_method(self) -> None:
        user = h.get_user_factory()()
        mfa_method_creator(user, "app")
        assert RequiredMFAPolicy().can_deactivate(user, "email") == (True, None)


@pytest.mark.django_db(transaction=True)
class TestMFAConcurrency:
    @override_settings(BASEAPP_AUTH_MFA_POLICY=POLICY_PATH + "GatedRequiredMFAPolicy")
    def test_concurrent_deactivations_keep_a_required_method(self) -> None:
        """
        Two requests remove one method each. The second one decides while the first is still
        running and acts once the first has committed. Without the lock both pass the policy and
        the user, who must keep MFA on, ends up with no method at all.
        """
        user = h.get_user_factory()()
        app = mfa_method_creator(user, "app")
        email = mfa_method_creator(user, "email", is_primary=False)
        codes = {"app": code_for(app), "email": code_for(email)}
        email_decided = threading.Event()
        email_done = threading.Event()
        app_decided = threading.Event()
        responses = {}

        def email_gate() -> None:
            email_decided.set()
            # Holds the lock while the app request tries to decide too; with the lock it can't.
            app_decided.wait(timeout=1)

        def app_gate() -> None:
            app_decided.set()
            email_done.wait(timeout=5)

        def deactivate(method: str, done: threading.Event | None = None) -> None:
            try:
                client = APIClient()
                client.force_authenticate(user)
                responses[method] = client.post(
                    f"{MFA_URL}{method}/deactivate/", {"code": codes[method]}
                )
            finally:
                if done:
                    done.set()
                connection.close()

        GatedRequiredMFAPolicy.gates = {"email": email_gate, "app": app_gate}
        try:
            email_thread = threading.Thread(target=deactivate, args=("email", email_done))
            email_thread.start()
            assert email_decided.wait(timeout=5)
            app_thread = threading.Thread(target=deactivate, args=("app",))
            app_thread.start()
            email_thread.join(timeout=10)
            app_thread.join(timeout=10)
        finally:
            GatedRequiredMFAPolicy.gates = {}

        assert responses["email"].status_code == status.HTTP_204_NO_CONTENT
        h.responseBadRequest(responses["app"])
        assert responses["app"].data["non_field_errors"] == [str(MFAPolicy.last_method_message)]
        assert list(user.mfa_methods.filter(is_active=True).values_list("name", flat=True)) == [
            "app"
        ]


class TestMFAViewsSetting:
    def test_defaults(self) -> None:
        assert mfa_views.get_mfa_view_class("activate") is trench_views.MFAMethodActivationView
        assert mfa_views.get_mfa_view_class("deactivate") is mfa_views.MFAMethodDeactivationView

    @override_settings(
        BASEAPP_AUTH_MFA_VIEWS={"deactivate": POLICY_PATH + "CustomDeactivationView"}
    )
    def test_override_with_a_dotted_path(self) -> None:
        assert mfa_views.get_mfa_view_class("deactivate") is CustomDeactivationView
        assert mfa_views.get_mfa_view_class("activate") is trench_views.MFAMethodActivationView

    @override_settings(BASEAPP_AUTH_MFA_VIEWS={"deactivate": CustomDeactivationView})
    def test_override_with_a_class(self) -> None:
        assert mfa_views.get_mfa_view_class("deactivate") is CustomDeactivationView

    @override_settings(BASEAPP_AUTH_MFA_VIEWS={"deactivation": CustomDeactivationView})
    def test_unknown_key_is_rejected(self) -> None:
        with pytest.raises(ImproperlyConfigured):
            mfa_views.get_mfa_view_class("deactivate")

    def test_unknown_name_is_rejected(self) -> None:
        with pytest.raises(KeyError):
            mfa_views.get_mfa_view_class("deactivation")

    @override_settings(BASEAPP_AUTH_MFA_VIEWS={"deactivate": CustomDeactivationView})
    def test_urlpatterns_use_the_overrides(self) -> None:
        views = {pattern.name: pattern.callback.view_class for pattern in get_urlpatterns()}
        assert views["mfa-deactivate"] is CustomDeactivationView
        assert views["mfa-activate-confirm"] is mfa_views.MFAMethodConfirmActivationView
        assert len(views) == len(mfa_views.DEFAULT_MFA_VIEWS)


class TestMFARequestCode:
    def test_post_sends_a_code_for_the_primary_method(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        r = user_client.post(f"{MFA_URL}code/request/")
        h.responseOk(r)

    def test_get_is_not_allowed(self, user_client) -> None:
        mfa_method_creator(user_client.user, "app")
        r = user_client.get(f"{MFA_URL}code/request/")
        h.responseMethodNotAllowed(r)

    def test_guest_cant_request_a_code(self, client) -> None:
        r = client.post(f"{MFA_URL}code/request/")
        h.responseUnauthorized(r)
