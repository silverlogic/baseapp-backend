# coding=utf-8
from importlib import reload as reload_module

from django.core.cache import cache
from django.test import SimpleTestCase
from django.test.client import Client, RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

from baseapp_devices import utils
from baseapp_devices.utils import get_and_set_user_agent, get_cache_key, get_user_agent
from user_agents.parsers import UserAgent

iphone_ua_string = "Mozilla/5.0 (iPhone; CPU iPhone OS 5_1 like Mac OS X) AppleWebKit/534.46 (KHTML, like Gecko) Version/5.1 Mobile/9B179 Safari/7534.48.3"
ipad_ua_string = "Mozilla/5.0(iPad; U; CPU iPhone OS 3_2 like Mac OS X; en-us) AppleWebKit/531.21.10 (KHTML, like Gecko) Version/4.0.4 Mobile/7B314 Safari/531.21.10"
long_ua_string = "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; InfoPath.3; .NET CLR 3.0.04506.30; .NET CLR 3.0.04506.648; .NET CLR 3.5.21022; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C; .NET4.0E)"


class MiddlewareTest(SimpleTestCase):

    def tearDown(self):
        for ua in [iphone_ua_string, ipad_ua_string, long_ua_string]:
            cache.delete(get_cache_key(ua))

    def test_middleware_assigns_user_agent(self):
        client = Client(HTTP_USER_AGENT=ipad_ua_string)
        response = client.get(reverse("user_agent_test"))
        self.assertIsInstance(response.context["user_agent"], UserAgent)

    def test_cache_is_set(self):
        request = RequestFactory(HTTP_USER_AGENT=iphone_ua_string).get("")
        user_agent = get_user_agent(request)
        self.assertIsInstance(user_agent, UserAgent)
        self.assertIsInstance(cache.get(get_cache_key(iphone_ua_string)), UserAgent)

    def test_empty_user_agent_does_not_cause_error(self):
        request = RequestFactory().get("")
        user_agent = get_user_agent(request)
        self.assertIsInstance(user_agent, UserAgent)

    def test_get_and_set_user_agent(self):
        # Test that get_and_set_user_agent attaches ``user_agent`` to request
        request = RequestFactory().get("")
        get_and_set_user_agent(request)
        self.assertIsInstance(request.user_agent, UserAgent)

    def test_get_cache_key(self):
        self.assertEqual(
            get_cache_key(long_ua_string),
            "django_user_agents.c226ec488bae76c60dd68ad58f03d729",
        )
        self.assertEqual(
            get_cache_key(iphone_ua_string),
            "django_user_agents.00705b9375a0e46e966515fe90f111da",
        )

    @override_settings(USER_AGENTS_CACHE=None)
    def test_disabled_cache(self):
        reload_module(utils)  # re-import with patched settings

        request = RequestFactory(HTTP_USER_AGENT=iphone_ua_string).get("")
        user_agent = get_user_agent(request)
        self.assertIsInstance(user_agent, UserAgent)
        self.assertIsNone(cache.get(get_cache_key(iphone_ua_string)))
