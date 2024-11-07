from typing import Any, Dict

from allauth.headless.adapter import DefaultHeadlessAdapter


class HeadlessAdapter(DefaultHeadlessAdapter):
    def serialize_user(self, user) -> Dict[str, Any]:
        # TODO: Add is_password_expired here
        return super(HeadlessAdapter, self).serialize_user(user)
