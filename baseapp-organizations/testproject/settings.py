from baseapp_core.tests.settings import *  # noqa
from django.utils.translation import gettext_lazy as _

# Application definition
INSTALLED_APPS += [
    "graphene_django",
    "baseapp_profiles",
    "baseapp_reactions",
    "baseapp_reports",
    "baseapp_pages",
    "baseapp_comments",
    "baseapp_auth",
    "baseapp_follows",
    "baseapp_blocks",
    "baseapp_organizations",
    "testproject.testapp",
]

ROOT_URLCONF = "testproject.urls"

# Auth
AUTH_USER_MODEL = "testapp.User"

LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("es", _("Spanish")), ("pt", _("Portuguese"))]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "baseapp_organizations.permissions.OrganizationsPermissionsBackend",
]


# Graphene
GRAPHENE["MIDDLEWARE"] = (
    "baseapp_profiles.graphql.middleware.CurrentProfileMiddleware",
) + GRAPHENE["MIDDLEWARE"]

BASEAPP_ORGANIZATIONS_ORGANIZATION_MODEL = "baseapp_organizations.Organization"
BASEAPP_PROFILES_PROFILE_MODEL = "baseapp_profiles.Profile"
BASEAPP_PROFILES_PROFILEUSERROLE_MODEL = "baseapp_profiles.ProfileUserRole"
