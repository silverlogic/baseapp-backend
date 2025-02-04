from django.core.signing import BadSignature, dumps, loads
from django.utils.encoding import DjangoUnicodeDecodeError, force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


class TokenGenerator(object):
    def make_token(self, obj):
        token = dumps(self.get_signing_value(obj), salt=self.key_salt)
        return urlsafe_base64_encode(force_bytes(token))

    def get_signing_value(self, obj):
        return obj.id

    def check_token(self, obj, token):
        value = self.decode_token(token)
        if value is None:
            return False
        return self.is_value_valid(obj, value)

    def is_value_valid(self, obj, value):
        return self.get_signing_value(obj) == value

    def decode_token(self, token):
        """Returns the decoded token or None if decoding fails."""
        try:
            decoded_token = urlsafe_base64_decode(token).decode("utf-8")
            return loads(decoded_token, salt=self.key_salt, max_age=self.max_age)
        except (BadSignature, DjangoUnicodeDecodeError, UnicodeDecodeError):
            return None

    @property
    def key_salt(self):
        raise NotImplementedError("Subclasses must define key_salt.")

    @property
    def max_age(self) -> int | None:
        return None
