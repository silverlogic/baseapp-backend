from typing import Any, Dict
from allauth.headless.adapter import DefaultHeadlessAdapter
from baseapp_auth.rest_framework.login.serializers import (
    LoginChangeExpiredPasswordRedirectSerializer,
)
from baseapp_auth.tokens import ChangeExpiredPasswordTokenGenerator
from django.conf import settings
from django.utils import timezone


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user) -> Dict[str, Any]:
        if user.password_expiry_date and user.password_expiry_date <= timezone.now():
            self.request.user = user
            token = ChangeExpiredPasswordTokenGenerator().make_token(self.request.user)
            url = settings.FRONT_CHANGE_EXPIRED_PASSWORD_URL.format(token=token)
            serializer = LoginChangeExpiredPasswordRedirectSerializer(
                data=dict(redirect_url=url), context={"request": self.request}
            )
            serializer.is_valid(raise_exception=True)
            return serializer.data
        return super(HeadlessAdapter, self).serialize_user(user)
