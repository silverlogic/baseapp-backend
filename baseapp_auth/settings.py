SIMPLE_JWT = {
    "TOKEN_OBTAIN_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtLoginSerializer",
    "TOKEN_REFRESH_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtRefreshSerializer",
}

JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"

# List of Django app labels for which permissions should be hidden/ignored.
# Expected format: a list of strings, each string being an app label as used in INSTALLED_APPS.
# Example:
#     PERMISSIONS_HIDE_APPS = ["auth", "contenttypes"]
PERMISSIONS_HIDE_APPS = []

# List of fully qualified model names for which permissions should be hidden/ignored.
# Expected format: a list of strings in the form "<app_label>.<model_name>" (lowercase model name).
# Example:
#     PERMISSIONS_HIDE_MODELS = ["auth.permission", "contenttypes.contenttype"]
PERMISSIONS_HIDE_MODELS = []
