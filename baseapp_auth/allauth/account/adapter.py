from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False

    def get_login_redirect_url(self, request):
        next_url = request.GET.get("next") or request.POST.get("next")
        if next_url and next_url.startswith("/admin/"):
            return next_url
        return "/admin/"

    def get_password_change_redirect_url(self, request):
        return "/admin/"

