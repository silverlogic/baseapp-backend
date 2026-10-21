from django.urls import URLPattern, path

from baseapp_auth.rest_framework.mfa.views import get_mfa_view_class

__all__ = [
    "get_urlpatterns",
    "urlpatterns",
]


def get_urlpatterns() -> tuple[URLPattern, ...]:
    """Build the MFA URLs from the views configured in `BASEAPP_AUTH_MFA_VIEWS`."""
    return (
        path(
            "<str:method>/activate/",
            get_mfa_view_class("activate").as_view(),
            name="mfa-activate",
        ),
        path(
            "<str:method>/activate/confirm/",
            get_mfa_view_class("activate_confirm").as_view(),
            name="mfa-activate-confirm",
        ),
        path(
            "<str:method>/deactivate/",
            get_mfa_view_class("deactivate").as_view(),
            name="mfa-deactivate",
        ),
        path(
            "<str:method>/codes/regenerate/",
            get_mfa_view_class("regenerate_codes").as_view(),
            name="mfa-regenerate-codes",
        ),
        path(
            "code/request/",
            get_mfa_view_class("request_code").as_view(),
            name="mfa-request-code",
        ),
        path("config/", get_mfa_view_class("config").as_view(), name="mfa-config-info"),
        path(
            "user-active-methods/",
            get_mfa_view_class("user_active_methods").as_view(),
            name="mfa-list-user-active-methods",
        ),
        path(
            "change-primary-method/",
            get_mfa_view_class("change_primary_method").as_view(),
            name="mfa-change-primary-method",
        ),
    )


urlpatterns = get_urlpatterns()
