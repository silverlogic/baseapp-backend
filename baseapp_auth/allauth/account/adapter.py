import posixpath
from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils.http import url_has_allowed_host_and_scheme


class AccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter for django-allauth.

    Signup behavior:
    - Headless API signup: Always enabled (controlled independently)
    - Admin/form-based signup: Controlled by ALLAUTH_ADMIN_SIGNUP_ENABLED

    Login/redirect behavior:
    - Redirects to Django admin after login
    - Validates 'next' parameter to only allow admin URLs
    - Redirects to admin after password changes

    Settings:
    - ALLAUTH_ADMIN_SIGNUP_ENABLED: Enable/disable admin signup (default: False)
    - ACCOUNT_LOGIN_REDIRECT_URL: Default login redirect (default: "admin:index")
    - ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL: Password change redirect
    """

    def is_open_for_signup(self, request):
        """
        Determine if signup is open based on the request type.

        - Headless API requests: Always allowed (returns True)
        - Admin/form-based requests: Controlled by ALLAUTH_ADMIN_SIGNUP_ENABLED

        This allows headless signup to work independently from admin signup.

        Args:
            request: The HTTP request object.

        Returns:
            bool: True if signup is allowed for this request type.
        """
        if request and (resolver_match := getattr(request, "resolver_match", None)):
            namespace = getattr(resolver_match, "namespace", "")
            if "headless" in namespace:
                return True

        return getattr(settings, "ALLAUTH_ADMIN_SIGNUP_ENABLED", False)

    def _validate_and_normalize_admin_url(self, request, next_url):
        """
        Validate and normalize a 'next' URL parameter to ensure it's a safe admin URL.

        This method performs security checks to prevent path traversal attacks and
        ensures the URL points to a valid admin view. It normalizes the path using
        posixpath.normpath to handle sequences like "/admin/../sensitive-page".

        Args:
            request: The HTTP request object.
            next_url: The URL string to validate and normalize.

        Returns:
            str: The normalized admin path if valid, None otherwise.
        """
        parsed = urlparse(next_url)
        normalized_path = posixpath.normpath(parsed.path)
        if normalized_path.startswith("/admin/"):
            normalized_url = (
                f"{parsed.scheme}://{parsed.netloc}{normalized_path}"
                if parsed.scheme
                else normalized_path
            )
            if url_has_allowed_host_and_scheme(
                normalized_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                try:
                    resolved = resolve(normalized_path)
                    if resolved.namespace == "admin":
                        return normalized_path
                except Resolver404:
                    pass
        return None

    def get_login_redirect_url(self, request):
        """
        Determine the redirect URL after successful login.

        This method implements the following redirect logic:
        1. If a 'next' parameter is provided and it's a safe admin URL, redirect there
        2. Otherwise, use ACCOUNT_LOGIN_REDIRECT_URL setting if available
        3. Fall back to admin:index if no setting is configured

        The 'next' parameter is checked for security (allowed host and scheme)
        and must point to an admin URL (/admin/) to be used.

        Args:
            request: The HTTP request object containing GET/POST parameters.

        Returns:
            str: The URL to redirect to after login (from ACCOUNT_LOGIN_REDIRECT_URL
                 setting, or admin:index by default, or the safe 'next' URL if provided
                 and valid).
        """
        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url:
            validated_url = self._validate_and_normalize_admin_url(request, next_url)
            if validated_url:
                return validated_url
        redirect_url = getattr(settings, "ACCOUNT_LOGIN_REDIRECT_URL", "admin:index")

        if redirect_url.startswith(("http://", "https://", "/")):  # NOSONAR
            return redirect_url
        return reverse(redirect_url)

    def get_password_change_redirect_url(self, request):
        """
        Determine the redirect URL after successful password change.

        Uses ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL setting if configured,
        otherwise defaults to account_change_password_done to render the
        password change done template.

        Args:
            request: The HTTP request object.

        Returns:
            str: The URL to redirect to after password change (from
                 ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL setting, or
                 account_change_password_done by default).
        """
        redirect_url = getattr(
            settings, "ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL", "account_change_password_done"
        )

        if redirect_url.startswith(("http://", "https://", "/")):  # NOSONAR
            return redirect_url
        try:
            return reverse(redirect_url)
        except Exception:
            return reverse("admin:index")
