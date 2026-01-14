from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.urls.exceptions import Resolver404


@pytest.fixture
def adapter():
    """Create an instance of AccountAdapter for testing."""
    from baseapp_auth.allauth.account.adapter import AccountAdapter

    return AccountAdapter()


@pytest.fixture
def request_factory():
    """Create a RequestFactory for generating test requests."""
    return RequestFactory()


class TestAccountAdapterIsOpenForSignup:
    """Tests for the is_open_for_signup method."""

    def test_signup_disabled_by_default(self, adapter, request_factory):
        """Test that signup is disabled when ALLAUTH_ADMIN_SIGNUP_ENABLED is not set."""
        request = request_factory.get("/")
        assert adapter.is_open_for_signup(request) is False

    @override_settings(ALLAUTH_ADMIN_SIGNUP_ENABLED=True)
    def test_signup_enabled_when_setting_is_true(self, adapter, request_factory):
        """Test that signup is enabled when ALLAUTH_ADMIN_SIGNUP_ENABLED is True."""
        request = request_factory.get("/")
        assert adapter.is_open_for_signup(request) is True

    @override_settings(ALLAUTH_ADMIN_SIGNUP_ENABLED=False)
    def test_signup_disabled_when_setting_is_false(self, adapter, request_factory):
        """Test that signup is disabled when ALLAUTH_ADMIN_SIGNUP_ENABLED is False."""
        request = request_factory.get("/")
        assert adapter.is_open_for_signup(request) is False


class TestAccountAdapterGetLoginRedirectUrl:
    """Tests for the get_login_redirect_url method security validation."""

    def test_redirects_to_default_when_no_next_parameter(self, adapter, request_factory):
        """Test that default redirect URL is used when no 'next' parameter is provided."""
        request = request_factory.get("/")
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == reverse("admin:index")

    @override_settings(ACCOUNT_LOGIN_REDIRECT_URL="admin:index")
    def test_uses_account_login_redirect_url_setting(self, adapter, request_factory):
        """Test that ACCOUNT_LOGIN_REDIRECT_URL setting is used when configured."""
        request = request_factory.get("/")
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == reverse("admin:index")

    @override_settings(ACCOUNT_LOGIN_REDIRECT_URL="/custom-redirect/")
    def test_uses_full_url_from_setting(self, adapter, request_factory):
        """Test that full URLs from ACCOUNT_LOGIN_REDIRECT_URL are returned directly."""
        request = request_factory.get("/")
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == "/custom-redirect/"

    def test_accepts_valid_admin_url_via_next_parameter(self, adapter, request_factory):
        """Test that valid admin URLs via 'next' parameter are accepted."""
        request = request_factory.get("/", {"next": "/admin/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == "/admin/"

    def test_accepts_valid_admin_url_via_post(self, adapter, request_factory):
        """Test that valid admin URLs via POST 'next' parameter are accepted."""
        request = request_factory.post("/", {"next": "/admin/users/user/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        # Path is normalized (trailing slash removed by normpath)
        assert url == "/admin/users/user"

    def test_rejects_non_admin_url(self, adapter, request_factory):
        """Test that non-admin URLs are rejected even if they pass host validation."""
        request = request_factory.get("/", {"next": "/accounts/profile/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        # Should fall back to default redirect
        assert url == reverse("admin:index")

    def test_rejects_path_traversal_attempt(self, adapter, request_factory):
        """Test that path traversal attacks are prevented."""
        request = request_factory.get("/", {"next": "/admin/../sensitive-page"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        # Path traversal should be normalized and fail namespace check
        assert url == reverse("admin:index")

    def test_rejects_path_traversal_with_multiple_dots(self, adapter, request_factory):
        """Test that multiple path traversal attempts are prevented."""
        request = request_factory.get("/", {"next": "/admin/../../etc/passwd"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == reverse("admin:index")

    def test_rejects_url_with_different_host(self, adapter, request_factory):
        """Test that URLs with different hosts are rejected."""
        request = request_factory.get("/", {"next": "http://evil.com/admin/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == reverse("admin:index")

    def test_rejects_invalid_url_that_does_not_resolve(self, adapter, request_factory):
        """Test that URLs that don't resolve to a view are rejected."""
        request = request_factory.get("/", {"next": "/admin/nonexistent-view-12345/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        with patch("baseapp_auth.allauth.account.adapter.resolve") as mock_resolve:
            mock_resolve.side_effect = Resolver404("URL not found")
            url = adapter.get_login_redirect_url(request)
            assert url == reverse("admin:index")

    def test_rejects_url_with_wrong_namespace(self, adapter, request_factory):
        """Test that URLs resolving to non-admin namespaces are rejected."""
        request = request_factory.get("/", {"next": "/admin/accounts/login/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        with patch("baseapp_auth.allauth.account.adapter.resolve") as mock_resolve:
            mock_resolved = MagicMock()
            mock_resolved.namespace = "accounts"  # Wrong namespace
            mock_resolve.return_value = mock_resolved
            url = adapter.get_login_redirect_url(request)
            assert url == reverse("admin:index")

    def test_accepts_url_with_admin_namespace(self, adapter, request_factory):
        """Test that URLs with admin namespace are accepted."""
        request = request_factory.get("/", {"next": "/admin/users/user/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        with patch("baseapp_auth.allauth.account.adapter.resolve") as mock_resolve:
            mock_resolved = MagicMock()
            mock_resolved.namespace = "admin"
            mock_resolve.return_value = mock_resolved
            url = adapter.get_login_redirect_url(request)
            # Path is normalized (trailing slash removed by normpath)
            assert url == "/admin/users/user"

    def test_requires_https_when_request_is_secure(self, adapter, request_factory):
        """Test that HTTPS is required when request is secure."""
        request = request_factory.get("/", {"next": "http://example.com/admin/"})
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=True)

        url = adapter.get_login_redirect_url(request)
        # HTTP URL should be rejected when request is secure
        assert url == reverse("admin:index")

    @override_settings(ACCOUNT_LOGIN_REDIRECT_URL="https://external-site.com/dashboard")
    def test_accepts_external_https_url_from_setting(self, adapter, request_factory):
        """Test that external HTTPS URLs from settings are accepted."""
        request = request_factory.get("/")
        request.get_host = MagicMock(return_value="example.com")
        request.is_secure = MagicMock(return_value=False)

        url = adapter.get_login_redirect_url(request)
        assert url == "https://external-site.com/dashboard"


class TestAccountAdapterGetPasswordChangeRedirectUrl:
    """Tests for the get_password_change_redirect_url method."""

    def test_redirects_to_default_when_no_setting(self, adapter, request_factory):
        """Test that default redirect URL is used when no setting is configured."""
        request = request_factory.get("/")
        url = adapter.get_password_change_redirect_url(request)
        # account_change_password_done may not exist, so adapter falls back to admin:index
        # We verify it returns a valid URL (either the intended one or the fallback)
        try:
            expected_url = reverse("account_change_password_done")
            assert url == expected_url
        except Exception:
            # If URL doesn't exist, adapter should fall back to admin:index
            assert url == reverse("admin:index")

    @override_settings(
        ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL="account_change_password_done"
    )  # NOSONAR
    def test_uses_account_password_change_redirect_url_setting(self, adapter, request_factory):
        """Test that ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL setting is used."""
        request = request_factory.get("/")
        url = adapter.get_password_change_redirect_url(request)
        # account_change_password_done may not exist, so adapter falls back to admin:index
        try:
            expected_url = reverse("account_change_password_done")
            assert url == expected_url
        except Exception:
            # If URL doesn't exist, adapter should fall back to admin:index
            assert url == reverse("admin:index")

    @override_settings(ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL="/custom-password-done/")  # NOSONAR
    def test_uses_full_url_from_setting(self, adapter, request_factory):
        """Test that full URLs from ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL are returned directly."""
        request = request_factory.get("/")
        url = adapter.get_password_change_redirect_url(request)
        assert url == "/custom-password-done/"

    @override_settings(ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL="https://external.com/done")  # NOSONAR
    def test_uses_external_url_from_setting(self, adapter, request_factory):
        """Test that external URLs from ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL are returned directly."""
        request = request_factory.get("/")
        url = adapter.get_password_change_redirect_url(request)
        assert url == "https://external.com/done"

    @override_settings(ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL="admin:index")  # NOSONAR
    def test_uses_url_name_from_setting(self, adapter, request_factory):
        """Test that URL names from ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL are reversed."""
        request = request_factory.get("/")
        url = adapter.get_password_change_redirect_url(request)
        assert url == reverse("admin:index")
