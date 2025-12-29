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
            if url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ) and next_url.startswith("/admin/"):
                # Validate that the URL resolves to a valid admin view
                try:
                    resolve(next_url)
                    return next_url
                except Resolver404:
                    # Invalid URL, fall through to default redirect
                    pass
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
        return reverse(redirect_url)
