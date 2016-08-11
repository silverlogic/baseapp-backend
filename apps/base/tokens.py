from django.core.signing import BadSignature, loads, dumps


class TokenGenerator(object):
    def make_token(self, obj):
        return dumps(self.get_signing_value(obj))

    def get_signing_value(self, obj):
        return obj.id

    def check_token(self, obj, token):
        try:
            value = loads(token)
        except BadSignature:
            return False

        return self.is_value_valid(obj, value)

    def is_value_valid(self, obj, value):
        return self.get_signing_value(obj) == value

    @property
    def key_salt(self):
        raise NotImplementedError('Subclasses must define key_salt.')
