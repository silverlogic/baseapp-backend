from django.core.signing import BadSignature, dumps, loads


class TokenGenerator(object):
    def make_token(self, obj):
        return dumps(self.get_signing_value(obj), salt=self.key_salt)

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
            return loads(token, salt=self.key_salt)
        except BadSignature:
            return None

    @property
    def key_salt(self):
        raise NotImplementedError("Subclasses must define key_salt.")
