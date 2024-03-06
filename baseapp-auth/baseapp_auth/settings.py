SIMPLE_JWT = {
    "TOKEN_OBTAIN_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtLoginSerializer",
    "TOKEN_REFRESH_SERIALIZER": "baseapp_auth.rest_framework.jwt.serializers.BaseJwtRefreshSerializer",
}

JWT_CLAIM_SERIALIZER_CLASS = "baseapp_auth.rest_framework.users.serializers.UserBaseSerializer"
