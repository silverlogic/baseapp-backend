from django.test import TestCase
from django.urls import reverse
from rest_framework import status

import baseapp_wagtail.base.rest_framework.tests.factories as f


class RedirectsAPIViewSetTests(TestCase):
    def test_redirect_api_request(self):
        f.RedirectFactory()
        response = self.client.get(reverse("baseappwagtailapi_base:redirects:listing"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["items"]), 1)

    def test_redirect_api_find_request(self):
        f.RedirectFactory(old_path="/old/path/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/old/path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))

    def test_redirect_api_find_request_with_locale(self):
        f.RedirectFactory(old_path="/es/old/path/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/es/old/path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))

    def test_redirect_api_find_request_with_unregistered_locale(self):
        f.RedirectFactory(old_path="/old/path/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/old/path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))

    def test_redirect_api_find_request_not_found(self):
        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/not/found/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), "not found")

    def test_redirect_api_find_request_with_case_insensitive_path(self):
        f.RedirectFactory(old_path="/old/path/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/Old/Path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))

    def test_redirect_api_find_request_with_case_insensitive_lower_path(self):
        f.RedirectFactory(old_path="/Old/Path/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/old/path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))

    def test_redirect_api_find_request_two_case_insensitive_paths(self):
        first_record = f.RedirectFactory(old_path="/Old/Path/")
        f.RedirectFactory(old_path="/olD/patH/")

        response = self.client.get(
            reverse("baseappwagtailapi_base:redirects:find"), {"html_path": "/old/path/"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.json().get("old_path"))
        self.assertIsNotNone(response.json().get("is_permanent"))
        self.assertIsNotNone(response.json().get("location"))
        self.assertEqual(response.json().get("id"), first_record.id)
