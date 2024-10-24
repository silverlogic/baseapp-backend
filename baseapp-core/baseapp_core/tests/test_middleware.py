from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from baseapp_core.middleware import HistoryMiddleware
from baseapp_core.tests.factories import UserFactory


class HistoryMiddlewareTest:
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = lambda request: HttpResponse("OK")
        self.middleware = HistoryMiddleware(self.get_response)

    @patch("baseapp_core.middleware.get_client_ip")
    @patch("baseapp_core.middleware.pghistory.context")
    def test_history_middleware_with_authenticated_user(self, mock_context, mock_get_client_ip):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        mock_get_client_ip.return_value = ("127.0.0.1", True)

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_context.assert_called_once_with(
            user=request.user.pk, url=request.path, clinet_ip="127.0.0.1", is_ip_routable=True
        )

    @patch("baseapp_core.middleware.get_client_ip")
    @patch("baseapp_core.middleware.pghistory.context")
    def test_history_middleware_with_anonymous_user(self, mock_context, mock_get_client_ip):
        request = self.factory.get("/some-path/")
        request.user = None
        mock_get_client_ip.return_value = ("127.0.0.1", True)

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_context.assert_called_once_with(
            user=None, url=request.path, clinet_ip="127.0.0.1", is_ip_routable=True
        )

    @patch("baseapp_core.middleware.get_client_ip")
    @patch("baseapp_core.middleware.pghistory.context")
    def test_history_middleware_with_non_routable_ip(self, mock_context, mock_get_client_ip):
        request = self.factory.get("/some-path/")
        request.user = UserFactory()
        mock_get_client_ip.return_value = ("127.0.0.1", False)

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_context.assert_called_once_with(
            user=request.user.pk, url=request.path, clinet_ip="127.0.0.1", is_ip_routable=False
        )

    @patch("baseapp_core.middleware.get_client_ip")
    @patch("baseapp_core.middleware.pghistory.context")
    def test_history_middleware_with_post_method(self, mock_context, mock_get_client_ip):
        request = self.factory.post("/some-path/")
        request.user = UserFactory()
        mock_get_client_ip.return_value = ("127.0.0.1", True)

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_context.assert_called_once_with(
            user=request.user.pk, url=request.path, clinet_ip="127.0.0.1", is_ip_routable=True
        )

    @patch("baseapp_core.middleware.get_client_ip")
    @patch("baseapp_core.middleware.pghistory.context")
    @override_settings(PGHISTORY_MIDDLEWARE_METHODS=("GET", "POST", "PATCH", "DELETE"))
    def test_history_middleware_with_unsupported_method(self, mock_context, mock_get_client_ip):
        request = self.factory.put("/some-path/")
        request.user = UserFactory()
        mock_get_client_ip.return_value = ("127.0.0.1", True)

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        mock_context.assert_not_called()
