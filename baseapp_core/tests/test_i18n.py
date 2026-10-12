from types import SimpleNamespace

import pytest
from django.utils import translation

from baseapp_core.i18n import get_user_language, group_by_language, user_language


def test_get_user_language_prefers_user_setting(settings) -> None:
    settings.LANGUAGE_CODE = "en-us"
    assert get_user_language(SimpleNamespace(preferred_language="pt-br")) == "pt-br"


def test_get_user_language_falls_back_to_language_code(settings) -> None:
    settings.LANGUAGE_CODE = "en-us"
    assert get_user_language(SimpleNamespace(preferred_language="")) == "en-us"
    assert get_user_language(None) == "en-us"


def test_user_language_activates_and_restores() -> None:
    translation.activate("en")
    with user_language(SimpleNamespace(preferred_language="es")):
        assert translation.get_language() == "es"
    assert translation.get_language() == "en"


@pytest.mark.parametrize("language", ["es", "pt-br"])
def test_user_language_translates_package_strings(language) -> None:
    with user_language(SimpleNamespace(preferred_language=language)):
        translated = translation.gettext("Case insensitive character")
    assert translated != "Case insensitive character"


def test_group_by_language_buckets_users(settings) -> None:
    settings.LANGUAGE_CODE = "en"
    es_1 = SimpleNamespace(preferred_language="es")
    es_2 = SimpleNamespace(preferred_language="es")
    default = SimpleNamespace(preferred_language=None)
    assert group_by_language([es_1, default, es_2]) == {"es": [es_1, es_2], "en": [default]}
