from graphql import assert_enum_value_name

from baseapp_core.graphql.translation import LanguagesEnum, language_enum_name


def test_language_codes_become_valid_enum_names() -> None:
    assert language_enum_name("en") == "en"
    assert language_enum_name("pt-br") == "pt_br"
    assert_enum_value_name(language_enum_name("pt-br"))


def test_enum_values_are_the_language_codes() -> None:
    assert LanguagesEnum.get("en").value == "en"
    assert LanguagesEnum.get("en") == LanguagesEnum.en
