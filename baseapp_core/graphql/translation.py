import graphene
from django.conf import settings
from django.utils.translation import gettext_lazy as _

LanguagesDict = dict(settings.LANGUAGES)


def language_enum_name(code: str) -> str:
    """GraphQL enum members can't contain "-": "pt-br" becomes "pt_br" (the value stays "pt-br")."""
    return code.replace("-", "_")


LanguagesEnum = graphene.Enum(
    "Languages",
    [(language_enum_name(code), code) for code, _label in settings.LANGUAGES],
    description=_("Languages available"),
)
