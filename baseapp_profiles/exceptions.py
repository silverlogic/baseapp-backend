from django.utils.functional import Promise


class ProfileMembershipError(Exception):
    """
    A membership or invitation operation was refused.

    `code` is a stable, machine-readable reason (`"last_admin"`, `"expired_invitation"`,
    ...) that the GraphQL mutations return as `extensions.code` and the REST views as
    `code`; `message` is the translated text for the user.
    """

    def __init__(self, message: str | Promise, code: str = "invalid") -> None:
        super().__init__(str(message))
        self.message = str(message)
        self.code = code
