from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

    def get_login_redirect_url(self, request):
        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url:
            if url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ) and next_url.startswith("/admin/"):
                return next_url
        return reverse("admin:index")

    def get_password_change_redirect_url(self, request):
        return reverse("admin:index")
