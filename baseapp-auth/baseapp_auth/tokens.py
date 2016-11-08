from apps.base.tokens import TokenGenerator


class ChangeEmailConfirmTokenGenerator(TokenGenerator):
    key_salt = 'change-email'

    def get_signing_value(self, user):
        return [user.id, user.new_email, user.is_new_email_confirmed]


class ChangeEmailVerifyTokenGenerator(TokenGenerator):
    key_salt = 'verify-email'

    def get_signing_value(self, user):
        return [user.id, user.new_email, user.is_new_email_confirmed]


class ConfirmEmailTokenGenerator(TokenGenerator):
    key_salt = 'confirm_email'

    def get_signing_value(self, user):
        return [user.pk, user.email]
