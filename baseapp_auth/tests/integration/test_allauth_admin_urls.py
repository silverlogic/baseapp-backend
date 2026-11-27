import pytest

import baseapp_auth.tests.helpers as h

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "admin_url,allauth_url",
    [
        ("/admin/login/", "/accounts/login/"),
        ("/admin/logout/", "/accounts/logout/"),
        ("/admin/password_change/", "/accounts/password/change/"),
    ],
)
def test_admin_auth_urls_redirect_to_allauth(django_client, admin_url, allauth_url) -> None:
    r = django_client.get(f"{admin_url}?next=/admin/")

    assert r.status_code in (301, 302)
    assert r["Location"].startswith(allauth_url)
    assert "next=/admin/" in r["Location"]


def test_allauth_login_page_renders(django_client) -> None:
    r = django_client.get("/accounts/login/")

    assert r.status_code == 200
    assert "account/login.html" in [t.name for t in r.templates]


def test_staff_can_log_in_to_admin_through_allauth(django_client) -> None:
    password = "testpassword123"  # NOSONAR
    UserFactory(email="staff@example.com", password=password, is_staff=True, is_superuser=True)

    r = django_client.post(
        "/accounts/login/?next=/admin/",
        {"login": "staff@example.com", "password": password},
    )

    assert r.status_code == 302
    assert r["Location"] == "/admin/"
    assert django_client.get("/admin/").status_code == 200
