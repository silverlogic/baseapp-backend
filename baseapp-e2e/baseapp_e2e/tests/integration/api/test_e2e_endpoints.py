import json

import pytest
import tests.factories as f
import tests.helpers as h
from django.contrib.auth import get_user_model
from django.core.serializers import serialize
from django.test import override_settings
from tests.mixins import ApiMixin

User = get_user_model()


pytestmark = pytest.mark.django_db


class TestBaseE2E(ApiMixin):
    endpoint_url = None

    @override_settings(E2E={"ENABLED": False})
    def test_e2e_disabled(self, client):
        if not self.endpoint_url:
            pytest.skip("No endpoint_url defined")
        else:
            r = client.post(self.endpoint_url)
            h.responseForbidden(r)


class TestLoadData(TestBaseE2E):
    endpoint_url = "/e2e/load-data"

    @pytest.fixture
    def data(self):
        f.UserFactory.create_batch(10)
        data = json.loads(serialize("json", User.objects.all()))

        User.objects.all().delete()
        return {
            "objects": data,
        }

    def test_load_data(self, data, client):
        assert User.objects.count() == 0
        r = client.post(self.endpoint_url, data=json.dumps(data), content_type="application/json")
        h.responseOk(r)

        assert User.objects.count() == len(data["objects"])


class TestFlushData(TestBaseE2E):
    endpoint_url = "/e2e/flush-data"

    def test_flush_data(self, client):
        objects = f.UserFactory.create_batch(10)
        assert User.objects.count() == len(objects)
        client.post(self.endpoint_url)
        assert User.objects.count() == 0


class TestLoadScript(TestBaseE2E):
    endpoint_url = "/e2e/load-script"

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
