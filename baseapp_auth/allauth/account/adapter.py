import posixpath
from urllib.parse import urlparse

from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils.http import url_has_allowed_host_and_scheme


class AccountAdapter(DefaultAccountAdapter):
    """
    Custom account adapter for django-allauth that configures authentication behavior.

    This adapter:
    - Disables public user signup (registration is handled through other means)
    - Redirects users to the Django admin after login and password changes
    - Allows redirect to admin URLs when specified via the 'next' parameter

    The signup is disabled because user registration should be managed through
    administrative processes or specific registration endpoints, not through
    the public allauth signup flow.

    Configuration:
    - ALLAUTH_ADMIN_SIGNUP_ENABLED: Controls whether signup is enabled (default: False)
    - ACCOUNT_LOGIN_REDIRECT_URL: Default redirect URL after login (default: "admin:index")
    - ACCOUNT_PASSWORD_CHANGE_REDIRECT_URL: Redirect URL after password change (default: "account_change_password_done")
    """

    def is_open_for_signup(self, request):
        """
        Determine if signup is open based on configuration.

        Checks the ALLAUTH_ADMIN_SIGNUP_ENABLED setting to determine if signup
        should be enabled. If not set, defaults to False to disable signup.

        Args:
            request: The HTTP request object.

        Returns:
            bool: True if signup is enabled (via ALLAUTH_ADMIN_SIGNUP_ENABLED),
                  False otherwise.
        """
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
        # Normalize the path to prevent path traversal attacks
        # This handles sequences like "/admin/../sensitive-page" -> "/sensitive-page"
        parsed = urlparse(next_url)
        # Use posixpath.normpath to normalize the path (handles .. and .)
        # Note: normpath removes trailing slashes, which is fine for security
        normalized_path = posixpath.normpath(parsed.path)
        # Ensure normalized path still starts with /admin/ after normalization
        if normalized_path.startswith("/admin/"):
            # Reconstruct URL with normalized path
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
                # Validate that the normalized URL resolves to a valid admin view
                try:
                    resolved = resolve(normalized_path)
                    # Ensure the resolved view belongs to the admin namespace
                    if resolved.namespace == "admin":
                        return normalized_path
                except Resolver404:
                    # Invalid URL, fall through to default redirect
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
        # Use ACCOUNT_LOGIN_REDIRECT_URL if configured, otherwise default to admin:index
        redirect_url = getattr(settings, "ACCOUNT_LOGIN_REDIRECT_URL", "admin:index")

        # If it's already a full URL or starts with /, return it directly
        # Otherwise, treat it as a URL name and reverse it
        if redirect_url.startswith(("http://", "https://", "/")):
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

        # If it's already a full URL or starts with /, return it directly
        # Otherwise, treat it as a URL name and reverse it
        if redirect_url.startswith(("http://", "https://", "/")):
            return redirect_url
        try:
            return reverse(redirect_url)
        except Exception:
            # If URL name doesn't exist, fall back to a safe default
            # This can happen if allauth URLs aren't fully configured
            return reverse("admin:index")
