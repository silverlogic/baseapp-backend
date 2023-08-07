from baseapp_auth.rest_framework.jwt.serializers import BaseJwtLoginSerializer
from django.conf import settings


class MyTokenObtainPairSerializer(BaseJwtLoginSerializer):
    _claim_serializer_class = getattr(settings, "JWT_CLAIM_SERIALIZER_CLASS", None)
