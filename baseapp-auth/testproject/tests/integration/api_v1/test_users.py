from datetime import timedelta

from django.utils import timezone

import pytest
from avatar.models import Avatar

from apps.referrals.models import UserReferral
from apps.referrals.utils import get_referral_code
from apps.users.tokens import ConfirmEmailTokenGenerator

import tests.factories as f
import tests.helpers as h
from tests.mixins import ApiMixin

pytestmark = pytest.mark.django_db


class TestUsersRetrieve(ApiMixin):
    view_name = "users-detail"

    def test_guest_cant_retreive(self, client):
        user = f.UserFactory()
        r = client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseUnauthorized(r)

    def test_user_can_retrieve(self, user_client):
        user = f.UserFactory()
        r = user_client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseOk(r)

    def test_object_keys_for_own_user(self, user_client):
        r = user_client.get(self.reverse(kwargs={"pk": user_client.user.pk}))
        h.responseOk(r)
        expected = {
            "id",
            "email",
            "is_email_verified",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
            "avatar",
            "first_name",
            "last_name",
        }
        actual = set(r.data.keys())
        assert expected == actual

    def test_object_keys_for_other_user(self, user_client):
        user = f.UserFactory()
        r = user_client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseOk(r)
        expected = {"id", "avatar", "first_name", "last_name"}
        actual = set(r.data.keys())
        assert expected == actual


class TestUsersUpdate(ApiMixin):
    view_name = "users-detail"

    def test_guest_cant_update(self, client):
        user = f.UserFactory()
        r = client.patch(self.reverse(kwargs={"pk": user.id}))
        h.responseUnauthorized(r)

    def test_user_can_update_self(self, user_client):
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}))
        h.responseOk(r)

    def test_user_cant_update_other_user(self, user_client):
        other_user = f.UserFactory()
        data = {"email": "test@email.co"}
        r = user_client.patch(self.reverse(kwargs={"pk": other_user.id}), data)
        h.responseForbidden(r)

    def test_user_cant_update_email(self, user_client):
        data = {"email": "test@email.co"}
        user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        user_client.user.refresh_from_db()
        assert user_client.user.email != "test@email.co"

    def test_can_update_referred_by_code_on_the_same_day_user_registered(self, user_client):
        user = f.UserFactory()
        data = {"referred_by_code": get_referral_code(user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseOk(r)
        user_client.user.refresh_from_db()
        assert user_client.user.referred_by.referrer == user

    def test_cant_update_referred_by_code_with_invalid_code(self, user_client):
        data = {"referred_by_code": "8182"}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["Invalid referral code."]

    def test_cant_update_referred_by_code_when_user_already_has_a_referrer(self, user_client):
        user = f.UserFactory()
        UserReferral.objects.create(referee=user_client.user, referrer=user)
        data = {"referred_by_code": get_referral_code(user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["You have already been referred by somebody."]

    def test_cant_update_referred_by_code_to_yourself(self, user_client):
        data = {"referred_by_code": get_referral_code(user_client.user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["You cannot refer yourself."]

    def test_cant_update_referred_by_code_after_the_day_the_user_registered(self, user_client):
        user_client.user.date_joined = timezone.now() - timedelta(days=1, hours=1)
        user_client.user.save()
        user = f.UserFactory()
        data = {"referred_by_code": get_referral_code(user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == [
            "You are no longer allowed to change who you were referred by."
        ]

    def test_can_upload_avatar(self, user_client, image_base64):
        data = {"avatar": image_base64}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.pk}), data)
        h.responseOk(r)
        assert Avatar.objects.exists()

    def test_can_clear_avatar(self, user_client, image_djangofile):
        Avatar.objects.create(user=user_client.user, primary=True, avatar=image_djangofile)
        data = {"avatar": None}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.pk}), data)
        h.responseOk(r)
        assert not Avatar.objects.exists()


class TestUsersList(ApiMixin):
    view_name = "users-list"

    def test_guest_cant_list(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_list(self, user_client):
        r = user_client.get(self.reverse())
        h.responseOk(r)

    def test_can_search(self, user_client):
        f.UserFactory(first_name="John", last_name="Smith")
        f.UserFactory(first_name="Bobby", last_name="Timbers")
        r = user_client.get(self.reverse(query_params={"q": "John Smith"}))
        h.responseOk(r)
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["first_name"] == "John"


class TestUsersMe(ApiMixin):
    view_name = "users-me"

    def test_as_anon(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_as_user(self, client):
        user = f.UserFactory()
        client.force_authenticate(user)
        r = client.get(self.reverse())
        h.responseOk(r)


class TestUsersChangePassword(ApiMixin):
    view_name = "users-change-password"

    @pytest.fixture
    def data(self):
        return {"current_password": "1234567890", "new_password": "0987654321"}

    def test_as_anon(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_change_password(self, client, data):
        user = f.UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    def test_password_is_set(self, client, data):
        user = f.UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        user.refresh_from_db()
        assert user.check_password(data["new_password"])

    def test_current_password_must_match(self, client, data):
        user = f.UserFactory(password="not current password")
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["current_password"] == ["That is not your current password."]

    def test_new_password_must_match_password_validations(self, client, data):
        f.PasswordValidationFactory()
        user = f.UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["new_password"] == [
            "This password must contain at least 1 special characters."
        ]


class TestConfirmEmail(ApiMixin):
    view_name = "users-confirm-email"

    @pytest.fixture
    def data(self):
        self.user = f.UserFactory(is_email_verified=False)
        return {"token": ConfirmEmailTokenGenerator().make_token(self.user)}

    def test_confirm_email(self, client, data):
        assert not self.user.is_email_verified
        r = client.post(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseOk(r)
        self.user.refresh_from_db()
        assert self.user.is_email_verified

    def test_confirm_email_invalid_token(self, client, data):
        data["token"] = "invalid-token"
        r = client.post(self.reverse(kwargs={"pk": self.user.pk}), data)
        h.responseBadRequest(r)

    def test_confirm_email_no_user(self, client, data):
        r = client.post(self.reverse(kwargs={"pk": self.user.pk + 1}), data)
        h.responseBadRequest(r)
