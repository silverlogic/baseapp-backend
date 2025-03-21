import json

import pytest
import swapper
import tests.helpers as h
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers import serialize
from django.test import TransactionTestCase, override_settings
from tests.mixins import ApiMixin

from baseapp_core.tests.factories import UserFactory

User = get_user_model()
Profile = swapper.load_model("baseapp_profiles", "Profile")


pytestmark = pytest.mark.django_db

TransactionTestCase.available_apps = {app_config.name for app_config in apps.get_app_configs()}


class TestBaseE2E(ApiMixin):
    endpoint_url = None

    @override_settings(
        E2E={"ENABLED": False}, REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES": []}
    )
    def test_e2e_disabled(self, client):
        if not self.endpoint_url:
            pytest.skip("No endpoint_url defined")
        else:
            r = client.post(self.endpoint_url)
            # breakpoint()
            h.responseUnauthorized(r)


class TestLoadData(TestBaseE2E):
    endpoint_url = "/e2e/load-data"

    @pytest.fixture
    def data(self):
        UserFactory.create_batch(10)
        data = json.loads(serialize("json", User.objects.all()))
        Profile.objects.all().delete()
        User.objects.all().delete()
        return {
            "objects": data,
        }

    @override_settings(REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES": []})
    def test_load_data(self, data, client):
        assert User.objects.count() == 0
        r = client.post(self.endpoint_url, data=json.dumps(data), content_type="application/json")
        h.responseOk(r)

        assert User.objects.count() == len(data["objects"])


class TestFlushData(TestBaseE2E):
    endpoint_url = "/e2e/flush-data"

    @override_settings(REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES": []})
    def test_flush_data(self, client):
        objects = UserFactory.create_batch(10)
        assert User.objects.count() == len(objects)
        client.post(self.endpoint_url)
        assert User.objects.count() == 0


class TestLoadScript(TestBaseE2E):
    endpoint_url = "/e2e/load-script"

    @override_settings(REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES": []})
    def test_load_script(self, client, monkeypatch):
        scripts = ["hello", "world"]
        expected_hello_user_count = 5
        expected_world_user_count = 10

        assert User.objects.count() == 0

        r = client.post(
            self.endpoint_url,
            data=json.dumps({"scripts": scripts}),
            content_type="application/json",
        )
        h.responseOk(r)
        assert User.objects.count() == expected_hello_user_count + expected_world_user_count

        # 2nd run / load
        r = client.post(
            self.endpoint_url,
            data=json.dumps({"scripts": scripts}),
            content_type="application/json",
        )
        h.responseOk(r)
        assert User.objects.count() == 2 * (expected_hello_user_count + expected_world_user_count)
