from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse
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
    """

    def is_open_for_signup(self, request):
        """
        Disable public user signup.

        Returns False to prevent users from registering through the standard
        allauth signup flow. User registration should be handled through
        administrative interfaces or dedicated registration endpoints.

        Args:
            request: The HTTP request object.

        Returns:
            bool: Always returns False to disable signup.
        """
        return False

    def get_login_redirect_url(self, request):
        """
        Determine the redirect URL after successful login.

        This method implements the following redirect logic:
        1. If a 'next' parameter is provided and it's a safe admin URL, redirect there
        2. Otherwise, redirect to the Django admin index page

        The 'next' parameter is checked for security (allowed host and scheme)
        and must point to an admin URL (/admin/) to be used.

        Args:
            request: The HTTP request object containing GET/POST parameters.

        Returns:
            str: The URL to redirect to after login (admin:index by default,
                 or the safe 'next' URL if provided and valid).
        """
        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url:
            if url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ) and next_url.startswith("/admin/"):
                return next_url
        return reverse("admin:index")

    def get_password_change_redirect_url(self, request):
        """
        Determine the redirect URL after successful password change.

        Redirects users to the standard password change done view after they
        successfully change their password, allowing the
        ``password_change_done.html`` template to be rendered.

        Args:
            request: The HTTP request object.

        Returns:
            str: The URL to redirect to after password change (password_change_done).
        """
        return reverse("password_change_done")
