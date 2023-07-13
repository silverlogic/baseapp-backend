from baseapp_auth.rest_framework.jwt.serializers import BaseJwtLoginSerializer
from baseapp_auth.rest_framework.users.serializers import UserBaseSerializer


class MyTokenObtainPairSerializer(BaseJwtLoginSerializer):
    claim_serializer_class = UserBaseSerializer
