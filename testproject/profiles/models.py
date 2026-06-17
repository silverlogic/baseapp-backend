from baseapp_profiles.models import AbstractProfile, AbstractProfileUserRole


class Profile(AbstractProfile):
    class Meta(AbstractProfile.Meta):
        pass


class ProfileUserRole(AbstractProfileUserRole):
    """
    Here you can customize the user <-> profile relationship.

    To customize the roles, you can override the ProfileRoles class like:

    class ProfileUserRole(AbstractProfileUserRole):
        class ProfileRoles(models.IntegerChoices):
            ADMIN = 1, _("admin")
            MANAGER = 2, _("manager")

            @property
            def description(self):
                return self.label
    """

    class Meta(AbstractProfileUserRole.Meta):
        pass
