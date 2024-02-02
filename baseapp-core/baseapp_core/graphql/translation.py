import graphene
from django.conf import settings
from django.utils.translation import gettext_lazy as _

LanguagesDict = dict(settings.LANGUAGES)

LanguagesEnum = graphene.Enum("Languages", settings.LANGUAGES, description=_("Languages available"))
