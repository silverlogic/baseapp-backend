import copy
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import Permission
from django.core.cache import cache

import baseapp_core.tests.factories as core_factories
from baseapp_core.tests.fixtures import DjangoClient
from baseapp_message_templates.registry import email_templates

DEFAULT_FILES = {
    "emails/tests/welcome.subject.txt.j2": (
        "{% if user.first_name %}Welcome, {{ user.first_name }}{% else %}Welcome{% endif %}\n"
        "  to   {{ site_name }}\n"
    ),
    "emails/tests/welcome.body.txt.j2": "Hi {{ user.first_name }}, A & B",
    "emails/tests/welcome.body.html.j2": "<p>{{ body_text|e }}</p>",
    "emails/tests/text-only.subject.txt.j2": "Text only {{ code }}",
    "emails/tests/text-only.body.txt.j2": "Your code is {{ code }}",
    "emails/tests/default.subject.txt.j2": "Default subject",
    "emails/tests/default.body.txt.j2": "Default body {{ code }}",
}


@pytest.fixture(autouse=True)
def isolated_email_templates() -> Generator[None, None, None]:
    """Each test starts with an empty registry; the project's registrations come back after."""
    saved = dict(email_templates._templates)
    email_templates.clear()
    cache.clear()
    yield
    email_templates.clear()
    email_templates._templates.update(saved)


@pytest.fixture
def email_template_files(tmp_path: Path, settings) -> Callable[[dict[str, str]], None]:
    """Serve template files from a temporary directory, for every configured engine.

    Writes ``DEFAULT_FILES``; call the returned function to add or replace files.
    """

    def write(files: dict[str, str]) -> None:
        for name, content in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    write(DEFAULT_FILES)
    templates = copy.deepcopy(settings.TEMPLATES)
    for engine in templates:
        engine["DIRS"] = [str(tmp_path), *engine.get("DIRS", [])]
    settings.TEMPLATES = templates
    return write


def grant(user: AbstractBaseUser, *codenames: str) -> None:
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="baseapp_message_templates", codename__in=codenames
        )
    )


@pytest.fixture
def staff_user() -> AbstractBaseUser:
    user = core_factories.UserFactory()
    grant(user, "view_emailtemplate", "change_emailtemplate", "send_test_emailtemplate")
    return user


@pytest.fixture
def staff_client(staff_user) -> DjangoClient:
    client = DjangoClient()
    client.force_login(staff_user)
    return client
