from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

import baseapp_auth.tests.helpers as h
from baseapp_auth.tests.factories import PasswordValidationFactory
from baseapp_auth.tests.mixins import ApiMixin
from baseapp_auth.utils.referral_utils import get_user_referral_model
from baseapp_referrals.utils import get_referral_code

User = get_user_model()
UserFactory = h.get_user_factory()

pytestmark = [pytest.mark.django_db, pytest.mark.referrals]

skip_if_no_referrals = pytest.mark.skipif(
    "baseapp_referrals" not in settings.INSTALLED_APPS, reason="No referrals app"
)

UserReferral = get_user_referral_model()


class TestUsersRetrieve(ApiMixin):
    view_name = "users-detail"

    def test_guest_cant_retrieve(self, client):
        user = UserFactory()
        r = client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseUnauthorized(r)

    def test_user_can_retrieve(self, user_client):
        user = UserFactory()
        r = user_client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseOk(r)

    def test_object_keys_for_own_user(self, user_client):
        r = user_client.get(self.reverse(kwargs={"pk": user_client.user.pk}))
        h.responseOk(r)
        expected = {
            "id",
            "profile",
            "email",
            "is_email_verified",
            "email_verification_required",
            "new_email",
            "is_new_email_confirmed",
            "referral_code",
            "phone_number",
            "preferred_language",
        }
        actual = set(r.data.keys())
        assert expected == actual

        profile_expected = {"id", "name", "image", "url_path"}
        profile_actual = set(r.data["profile"].keys())
        assert profile_expected == profile_actual

    def test_object_keys_for_other_user(self, user_client):
        user = UserFactory()
        r = user_client.get(self.reverse(kwargs={"pk": user.pk}))
        h.responseOk(r)
        expected = {"id", "profile", "phone_number"}
        actual = set(r.data.keys())
        assert expected == actual

        profile_expected = {"id", "name", "image", "url_path"}
        profile_actual = set(r.data["profile"].keys())
        assert profile_expected == profile_actual


class TestUsersUpdate(ApiMixin):
    view_name = "users-detail"

    def test_guest_cant_update(self, client):
        user = UserFactory()
        r = client.patch(self.reverse(kwargs={"pk": user.id}))
        h.responseUnauthorized(r)

    def test_user_can_update_self(self, user_client):
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}))
        h.responseOk(r)

    def test_user_cant_update_other_user(self, user_client):
        other_user = UserFactory()
        data = {"email": "test@email.co"}
        r = user_client.patch(self.reverse(kwargs={"pk": other_user.id}), data)
        h.responseForbidden(r)

    def test_user_cant_update_email(self, user_client):
        data = {"email": "test@email.co"}
        user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        user_client.user.refresh_from_db()
        assert user_client.user.email != "test@email.co"

    @skip_if_no_referrals
    def test_can_update_referred_by_code_on_the_same_day_user_registered(self, user_client):
        user = UserFactory()
        data = {"referred_by_code": get_referral_code(user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseOk(r)
        user_client.user.refresh_from_db()
        assert user_client.user.referred_by.referrer == user

    @skip_if_no_referrals
    def test_cant_update_referred_by_code_with_invalid_code(self, user_client):
        data = {"referred_by_code": "8182"}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["Invalid referral code."]

    @skip_if_no_referrals
    def test_cant_update_referred_by_code_when_user_already_has_a_referrer(self, user_client):
        user = UserFactory()
        UserReferral.objects.create(referee=user_client.user, referrer=user)
        data = {"referred_by_code": get_referral_code(user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["You have already been referred by somebody."]

    @skip_if_no_referrals
    def test_cant_update_referred_by_code_to_yourself(self, user_client):
        data = {"referred_by_code": get_referral_code(user_client.user)}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.id}), data)
        h.responseBadRequest(r)
        assert r.data["referred_by_code"] == ["You cannot refer yourself."]

    @skip_if_no_referrals
    def test_cant_update_referred_by_code_after_the_day_the_user_registered(self, user_client):
        user_client.user.date_joined = timezone.now() - timedelta(days=1, hours=1)
        user_client.user.save()
        user = UserFactory()
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
        user_client.user.profile.refresh_from_db()
        assert bool(user_client.user.profile.image) is True

    def test_can_clear_avatar(self, user_client, image_djangofile):
        user_client.user.profile.image = image_djangofile
        user_client.user.profile.save()
        data = {"avatar": None}
        r = user_client.patch(self.reverse(kwargs={"pk": user_client.user.pk}), data)
        h.responseOk(r)
        user_client.user.profile.refresh_from_db()
        assert not user_client.user.profile.image


class TestUsersList(ApiMixin):
    view_name = "users-list"

    def test_guest_cant_list(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_list(self, user_client):
        r = user_client.get(self.reverse())
        h.responseOk(r)

    def test_can_search(self, user_client):
        UserFactory(first_name="John", last_name="Smith")
        UserFactory(first_name="Bobby", last_name="Timbers")
        r = user_client.get(self.reverse(query_params={"q": "John Smith"}))
        h.responseOk(r)
        assert len(r.data["results"]) == 1
        assert r.data["results"][0]["profile"]["name"] == "John Smith"


class TestUsersMe(ApiMixin):
    view_name = "users-me"

    def test_as_anon(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_as_user(self, client):
        user = UserFactory()
        client.force_authenticate(user)
        r = client.get(self.reverse())
        h.responseOk(r)


class TestUsersDeleteAccount(ApiMixin):
    view_name = "users-delete-account"

    def test_as_anon(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_non_admin_can_delete_account(self, user_client):
        user_client.user.is_superuser = False
        user_client.user.save()
        user_id = user_client.user.id
        r = user_client.delete(self.reverse())
        h.responseNoContent(r)
        assert User.objects.filter(id=user_id).exists() is False

    def test_admin_can_only_deactivate_account(self, user_client):
        user_client.user.is_superuser = True
        user_client.user.save()
        user_id = user_client.user.id
        r = user_client.delete(self.reverse())
        h.responseNoContent(r)
        assert User.objects.filter(id=user_id, is_active=False).exists() is True


class TestUsersChangePassword(ApiMixin):
    view_name = "users-change-password"

    @pytest.fixture
    def data(self):
        return {"current_password": "1234567890", "new_password": "0987654321"}

    def test_as_anon(self, client):
        r = client.post(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_change_password(self, client, data):
        user = UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)

    def test_password_is_set(self, client, data):
        user = UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseOk(r)
        user.refresh_from_db()
        assert user.check_password(data["new_password"])

    def test_current_password_must_match(self, client, data):
        user = UserFactory(password="not current password")
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["current_password"] == ["That is not your current password."]

    def test_new_password_must_match_password_validations(self, client, data):
        PasswordValidationFactory()
        user = UserFactory(password=data["current_password"])
        client.force_authenticate(user)
        r = client.post(self.reverse(), data)
        h.responseBadRequest(r)
        assert r.data["new_password"] == [
            "This password must contain at least 1 special characters."
        ]

    def test_fails_nicely_on_invalid_json(self, user_client):
        invalid_json_str = """{
    "current_password": "1234",
    "new_password": "1234
}
"""
        r = user_client.generic(
            "POST",
            self.reverse(),
            data=invalid_json_str,
            content_type="application/json",
        )
        h.responseBadRequest(r)
        # The request should fail to parse the invalid json and pass an empty dict
        # to the endpoint request object. So we should see serializer field errors here
        assert r.data["current_password"] == ["This field is required."]
        assert r.data["new_password"] == ["This field is required."]


class TestUserPermission(ApiMixin):
    view_name = "users-permissions"

    def test_can_get_their_permission(self, user_client):
        admin_content_type = ContentType.objects.filter(app_label="admin").first()
        perm = Permission.objects.create(
            codename="test_unique_perm", name="Test", content_type=admin_content_type
        )
        user_client.user.user_permissions.add(perm)
        r = user_client.get(self.reverse())
        h.responseOk(r)

    def test_guest_cannot_get_permission(self, client):
        r = client.get(self.reverse())
        h.responseUnauthorized(r)

    def test_user_can_check_their_permission(self, user_client):
        admin_content_type = ContentType.objects.filter(app_label="admin").first()
        perm = Permission.objects.create(
            codename="test_unique_perm", name="Test", content_type=admin_content_type
        )
        user_client.user.user_permissions.add(perm)
        r = user_client.post(self.reverse(), {"perm": "admin.test_unique_perm"})
        h.responseOk(r)
        assert r.data["has_perm"]

    def test_user_get_false_without_permission(self, user_client):
        r = user_client.post(self.reverse(), {"perm": "admin.test_unique_perm"})
        h.responseOk(r)
        assert not r.data["has_perm"]


class TestUserPermissionList(ApiMixin):
    view_name = "user-permissions-list"

    def test_guest_cannot_get_user_permissions(self, client):
        content_type = ContentType.objects.all().first()
        perm = Permission.objects.filter(content_type_id=content_type).first()
        user = UserFactory()
        user.user_permissions.add(perm)
        r = client.get(self.reverse(kwargs={"user_pk": user.pk}))
        h.responseUnauthorized(r)

    def test_user_without_perm_cannot_get_user_permissions(self, user_client):
        content_type = ContentType.objects.all().first()
        perm = Permission.objects.filter(content_type_id=content_type).first()
        user = UserFactory()
        user.user_permissions.add(perm)
        r = user_client.get(self.reverse(kwargs={"user_pk": user.pk}))
        h.responseBadRequest(r)
        assert "You do not have permission to perform this action." == r.data["detail"]

    def test_user_with_perm_can_get_user_permissions(self, user_client):
        content_type = ContentType.objects.all().first()
        perm = Permission.objects.filter(content_type_id=content_type).first()
        user = UserFactory()
        user.user_permissions.add(perm)
        p = Permission.objects.get(codename="change_user")
        p.content_type.app_label = "users"
        p.content_type.save()
        user_client.user.user_permissions.add(p)
        user_client.user.refresh_from_db()
        r = user_client.get(self.reverse(kwargs={"user_pk": user.pk}))
        h.responseOk(r)

    def test_user_with_perm_can_up_user_permissions(self, user_client):
        content_type = ContentType.objects.all().first()
        perm = Permission.objects.filter(content_type_id=content_type).first()
        user = UserFactory()
        user.user_permissions.add(perm)
        p = Permission.objects.get(codename="change_user")
        p.content_type.app_label = "users"
        p.content_type.save()
        user_client.user.user_permissions.add(p)
        r = user_client.post(
            self.reverse(kwargs={"user_pk": user.pk}), data={"codename": "delete_user"}
        )
        h.responseCreated(r)
        assert user.user_permissions.count() == 2

    def test_user_with_perm_can_set_user_permissions(self, user_client):
        user = UserFactory()
        p = Permission.objects.get(codename="change_user")
        p.content_type.app_label = "users"
        p.content_type.save()
        user_client.user.user_permissions.add(p)
        r = user_client.post(
            self.reverse(kwargs={"user_pk": user.pk}),
            data={"permissions": ["change_user", "delete_user"]},
        )
        h.responseCreated(r)
        assert user.user_permissions.count() == 2
