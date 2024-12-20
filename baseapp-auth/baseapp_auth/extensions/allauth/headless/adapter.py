from typing import Any, Dict

from allauth.headless.adapter import DefaultHeadlessAdapter
from baseapp_auth.rest_framework.users.serializers import UserSerializer


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user) -> Dict[str, Any]:
        # TODO: MFA Follow Up | Expired Password Refactor
        # Add is_password_expired here. See LoginPasswordExpirationMixin
        data = super(HeadlessAdapter, self).serialize_user(user)
        serializer = UserSerializer(user, context={"request": self.request})
        return serializer.data | data
