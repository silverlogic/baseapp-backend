from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.middleware import CurrentProfileMiddleware
from baseapp_profiles.tests.factories import ProfileFactory, ProfileUserRoleFactory


class CurrentProfileMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = CurrentProfileMiddleware(lambda request: HttpResponse("OK"))

    def test_set_user_current_profile(self):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        request.META["HTTP_CURRENT_PROFILE"] = request.user.profile.relay_id
        self.middleware(request)
        self.assertEqual(request.user.current_profile, request.user.profile)

    def test_cant_use_anothers_profile(self):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        profile = ProfileFactory()
        request.META["HTTP_CURRENT_PROFILE"] = profile.relay_id
        self.middleware(request)
        self.assertEqual(request.user.current_profile, None)

    def test_members_can_use(self):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        profile = ProfileFactory()
        ProfileUserRoleFactory(user=request.user, profile=profile)
        request.META["HTTP_CURRENT_PROFILE"] = profile.relay_id
        self.middleware(request)
        self.assertEqual(request.user.current_profile, profile)

    def test_bad_profile_id(self):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        ProfileFactory()
        request.META["HTTP_CURRENT_PROFILE"] = "InvalidBase64%"
        self.middleware(request)
        self.assertEqual(request.user.current_profile, None)

    def test_default_profile_when_not_passing_header(self):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        self.middleware(request)
        self.assertEqual(request.user.current_profile, request.user.profile)
